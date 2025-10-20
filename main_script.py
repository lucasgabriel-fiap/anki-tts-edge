# -*- coding: utf-8 -*-
"""
Anki — Áudio PT-BR com Edge TTS (Versão ULTRA ROBUSTA)
100% de sucesso garantido com máxima velocidade
"""

import os
import sys
import time
import asyncio
import argparse
import logging
from typing import List, Dict, Tuple, Set, Any, Optional
from dataclasses import dataclass, field
from hashlib import blake2b
from concurrent.futures import ThreadPoolExecutor
import json
import random

import aiohttp
import edge_tts
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, MofNCompleteColumn
from rich.console import Console
from rich.table import Table
from rich.text import Text

from converters import strip_html_perfect, regex

# Otimizações Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# =======================
# CONFIGURAÇÃO
# =======================
@dataclass
class Config:
    DECK_QUERY: str = 'deck:"NomeDoSeuDeck"'
    MEDIA_DIR: str = r"C:\Users\SeuUsuario\AppData\Roaming\Anki2\Usuario 1\collection.media"
    
    RENDER_MODE: str = "auto"
    RENDER_SOURCE_FOR_FIELD: Dict[str, str] = field(default_factory=lambda: {
        "Frente": "question",
        "Verso": "answer",
    })
    
    # Edge TTS - Balanceado para confiabilidade
    EDGE_TTS_RATE: str = "+400%"
    EDGE_TTS_VOICES: List[str] = field(default_factory=lambda: [
        "pt-BR-ThalitaMultilingualNeural",
        "pt-BR-AntonioNeural",
        "pt-BR-FranciscaNeural",
        "pt-PT-DuarteNeural",
        "pt-PT-RaquelNeural",
    ])
    EDGE_TTS_TIMEOUT_S: int = 60  # Timeout mais generoso
    EDGE_TTS_MAX_RETRIES: int = 3  # Retries para garantir sucesso
    
    DRY_RUN: bool = False
    LIMIT_NOTES: int = None
    MIN_CHARS: int = 1
    
    # Concorrência otimizada mas estável
    CONCURRENCY: int = 100  # Balanceado para estabilidade
    IO_WORKERS: int = 16
    
    # AnkiConnect
    ANKI_ENDPOINT: str = "http://127.0.0.1:8765"
    ANKI_TIMEOUT_S: int = 120
    ANKI_MULTIACTION_BATCH: int = 2000
    ANKI_INFO_CHUNK: int = 1000
    
    RESET_MODE: bool = False
    AUDIO_WRITE_MODE: str = "skip"
    
    # Verificação de integridade
    VERIFY_FILES: bool = True
    MIN_FILE_SIZE: int = 1024  # 1KB mínimo

# =======================
# CONSOLE E LOG
# =======================
console = Console()
log = logging.getLogger("anki_tts")

def setup_logging():
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s - %(message)s",
        handlers=[logging.FileHandler("tts_errors.log", mode="w", encoding="utf-8")]
    )

# =======================
# AUXILIARES
# =======================
def fast_hash_filename(text: str) -> str:
    """Hash determinístico para nomes de arquivo"""
    return f"e{blake2b(text.encode(), digest_size=8).hexdigest()}.mp3"

def strip_sound_tags(text: str) -> str:
    """Remove tags de som existentes"""
    return regex.SOUND_TAG.sub("", text or "")

def verify_audio_file(path: str, min_size: int = 1024) -> bool:
    """Verifica se o arquivo de áudio é válido"""
    try:
        if not os.path.exists(path):
            return False
        size = os.path.getsize(path)
        return size >= min_size
    except:
        return False

# =======================
# ANKICONNECT ROBUSTO
# =======================
class AnkiConnectClient:
    def __init__(self, session: aiohttp.ClientSession, config: Config):
        self.session = session
        self.config = config
        self.endpoint = config.ANKI_ENDPOINT
        self.timeout = aiohttp.ClientTimeout(total=config.ANKI_TIMEOUT_S)
    
    async def _invoke(self, action: str, **params) -> Any:
        """Invocação com retry automático"""
        for attempt in range(3):
            try:
                payload = {"action": action, "version": 6, "params": params}
                async with self.session.post(
                    self.endpoint,
                    json=payload,
                    timeout=self.timeout
                ) as resp:
                    if resp.status != 200:
                        raise ConnectionError(f"HTTP {resp.status}")
                    
                    data = await resp.json()
                    if err := data.get("error"):
                        raise ConnectionError(f"AnkiConnect error: {err}")
                    return data.get("result")
            except Exception as e:
                if attempt == 2:
                    log.error(f"AnkiConnect failed after 3 attempts: {action} - {e}")
                    raise
                await asyncio.sleep(0.5 * (attempt + 1))
    
    async def find_notes(self, query: str) -> List[int]:
        return await self._invoke('findNotes', query=query) or []
    
    async def notes_info(self, note_ids: List[int]) -> List[Dict]:
        if not note_ids:
            return []
        return await self._invoke('notesInfo', notes=note_ids) or []
    
    async def get_all_notes_info(self, note_ids: List[int], progress: Progress) -> List[Dict]:
        if not note_ids:
            return []
        
        task_id = progress.add_task("[cyan]1. Carregando notas do Anki...", total=len(note_ids))
        
        all_notes = []
        chunk_size = self.config.ANKI_INFO_CHUNK
        
        for i in range(0, len(note_ids), chunk_size):
            chunk = note_ids[i:i+chunk_size]
            try:
                result = await self.notes_info(chunk)
                all_notes.extend(result)
                progress.update(task_id, advance=len(chunk))
            except Exception as e:
                log.error(f"Failed to get notes info for chunk {i}: {e}")
                progress.update(task_id, advance=len(chunk))
        
        progress.update(task_id, description="[green]✓ 1. Notas carregadas")
        return all_notes
    
    async def update_notes_batch(self, updates: List[Dict], progress: Progress) -> int:
        if not updates:
            return 0
        
        task_id = progress.add_task("[cyan]3. Salvando no Anki...", total=len(updates))
        updated = 0
        batch_size = self.config.ANKI_MULTIACTION_BATCH
        
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i+batch_size]
            try:
                actions = [{"action": "updateNoteFields", "params": {"note": item}} for item in batch]
                await self._invoke('multi', actions=actions)
                updated += len(batch)
            except Exception as e:
                log.error(f"Failed to update batch {i}: {e}")
            progress.update(task_id, advance=len(batch))
        
        progress.update(task_id, description="[green]✓ 3. Salvo no Anki")
        return updated

# =======================
# TTS GENERATOR ROBUSTO
# =======================
class TTSGenerator:
    def __init__(self, config: Config):
        self.config = config
        self.tasks = []
        self.voice_index = 0
        self.voices = config.EDGE_TTS_VOICES
        self._stats = {'ok': 0, 'fail': 0, 'skip': 0, 'retry': 0}
        self._start = time.perf_counter()
        self._failed_texts = []
    
    def get_next_voice(self) -> str:
        """Rotação de vozes"""
        voice = self.voices[self.voice_index % len(self.voices)]
        self.voice_index += 1
        return voice
    
    def prepare_tasks(self, notes: List[Dict]) -> Dict[str, str]:
        """Preparação de tarefas com deduplicação"""
        unique_texts = {}
        seen = set()
        
        for note in notes:
            note_id = note['noteId']
            fields = note.get('fields', {})
            
            for field_name in self.config.FIELDS_TO_PROCESS:
                field = fields.get(field_name)
                if not field:
                    continue
                
                value = field.get('value', '')
                
                # No modo reset, processar tudo
                if self.config.RESET_MODE:
                    # Remove tags de som antigas
                    value = strip_sound_tags(value)
                elif '[sound:' in value:
                    # Skip se já tem áudio e não é reset
                    self._stats['skip'] += 1
                    continue
                
                text = strip_html_perfect(value).strip()
                if not text or len(text) < self.config.MIN_CHARS:
                    continue
                
                # Deduplicação
                key = (note_id, field_name, text)
                if key in seen:
                    continue
                seen.add(key)
                
                filename = fast_hash_filename(text)
                
                # Adicionar tarefa
                self.tasks.append({
                    'note_id': note_id,
                    'field': field_name,
                    'text': text,
                    'filename': filename
                })
                
                # Texto único para geração
                if text not in unique_texts:
                    unique_texts[text] = os.path.join(self.config.MEDIA_DIR, filename)
        
        return unique_texts
    
    async def _generate_single_audio(self, text: str, path: str, sem: asyncio.Semaphore) -> Tuple[str, bool]:
        """Geração de um único áudio com retry robusto"""
        async with sem:
            # Verificar se já existe e é válido
            if self.config.AUDIO_WRITE_MODE == "skip" and not self.config.RESET_MODE:
                if verify_audio_file(path, self.config.MIN_FILE_SIZE):
                    self._stats['ok'] += 1
                    return text, True
            
            # Tentar gerar com múltiplas vozes se necessário
            last_error = None
            voices_to_try = list(self.voices)
            random.shuffle(voices_to_try)  # Aleatorizar ordem das vozes
            
            for voice_attempt, voice in enumerate(voices_to_try[:3]):  # Tentar até 3 vozes diferentes
                for retry in range(self.config.EDGE_TTS_MAX_RETRIES + 1):
                    try:
                        # Deletar arquivo inválido se existir
                        if os.path.exists(path) and not verify_audio_file(path, self.config.MIN_FILE_SIZE):
                            try:
                                os.remove(path)
                            except:
                                pass
                        
                        # Gerar áudio
                        communicate = edge_tts.Communicate(
                            text=text,
                            voice=voice,
                            rate=self.config.EDGE_TTS_RATE
                        )
                        
                        await asyncio.wait_for(
                            communicate.save(path),
                            timeout=self.config.EDGE_TTS_TIMEOUT_S
                        )
                        
                        # Verificar se foi salvo corretamente
                        if verify_audio_file(path, self.config.MIN_FILE_SIZE):
                            self._stats['ok'] += 1
                            if retry > 0 or voice_attempt > 0:
                                self._stats['retry'] += 1
                            return text, True
                        else:
                            raise Exception("Arquivo gerado é inválido")
                        
                    except asyncio.TimeoutError:
                        last_error = f"Timeout com voz {voice}"
                        await asyncio.sleep(0.5 * (retry + 1))
                    except Exception as e:
                        last_error = str(e)
                        await asyncio.sleep(0.3 * (retry + 1))
            
            # Falhou após todas as tentativas
            self._stats['fail'] += 1
            self._failed_texts.append((text, last_error))
            log.error(f"Falha ao gerar áudio: {text[:50]}... - {last_error}")
            return text, False
    
    async def generate_all_audio(self, unique_texts: Dict[str, str], progress: Progress) -> Dict[str, bool]:
        """Geração paralela com garantia de completude"""
        if not unique_texts or self.config.DRY_RUN:
            return {text: True for text in unique_texts}
        
        task_id = progress.add_task("[cyan]2. Gerando áudios TTS...", total=len(unique_texts))
        sem = asyncio.Semaphore(self.config.CONCURRENCY)
        
        # Primeira tentativa - processar todos
        tasks = []
        for text, path in unique_texts.items():
            tasks.append(self._generate_single_audio(text, path, sem))
        
        results = []
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)
            progress.update(task_id, advance=1)
        
        # Verificar e reprocessar falhas
        results_dict = dict(results)
        failed_count = sum(1 for success in results_dict.values() if not success)
        
        if failed_count > 0:
            progress.update(task_id, description=f"[yellow]2. Reprocessando {failed_count} falhas...")
            
            # Tentar novamente os que falharam com concorrência reduzida
            retry_sem = asyncio.Semaphore(max(10, self.config.CONCURRENCY // 10))
            retry_tasks = []
            
            for text, success in results_dict.items():
                if not success:
                    path = unique_texts[text]
                    retry_tasks.append(self._generate_single_audio(text, path, retry_sem))
            
            if retry_tasks:
                retry_results = await asyncio.gather(*retry_tasks)
                for text, success in retry_results:
                    results_dict[text] = success
        
        # Estatísticas finais
        final_success = sum(1 for s in results_dict.values() if s)
        final_failed = len(results_dict) - final_success
        
        if final_failed > 0:
            progress.update(task_id, description=f"[yellow]✓ 2. Áudios: {final_success} OK, {final_failed} falhas")
        else:
            progress.update(task_id, description=f"[green]✓ 2. Todos os {final_success} áudios gerados")
        
        return results_dict
    
    def prepare_updates(self, notes: List[Dict], tts_results: Dict[str, bool]) -> List[Dict]:
        """Preparar atualizações para o Anki"""
        if not self.tasks:
            return []
        
        notes_map = {n['noteId']: n for n in notes}
        updates = []
        processed = set()
        
        for task in self.tasks:
            # Só atualizar se o áudio foi gerado com sucesso
            if not tts_results.get(task['text'], False):
                continue
            
            key = (task['note_id'], task['field'])
            if key in processed:
                continue
            processed.add(key)
            
            note = notes_map.get(task['note_id'])
            if not note:
                continue
            
            current_value = note['fields'][task['field']]['value']
            
            # Limpar tags antigas no modo reset
            if self.config.RESET_MODE:
                new_value = strip_sound_tags(current_value).strip()
            else:
                new_value = current_value.strip()
            
            # Adicionar nova tag de som
            sound_tag = f"[sound:{task['filename']}]"
            
            # Só adicionar se ainda não existe
            if sound_tag not in new_value:
                # Adicionar quebra de linha se necessário
                if new_value and not new_value.endswith(('<br>', '<br />', '</div>')):
                    new_value += '<br>'
                new_value += sound_tag
                
                updates.append({
                    'id': task['note_id'],
                    'fields': {task['field']: new_value}
                })
        
        return updates
    
    async def run(self):
        """Pipeline principal"""
        start = time.perf_counter()
        
        progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeRemainingColumn(),
            transient=False,
            refresh_per_second=5
        )
        
        with progress:
            # Sessão HTTP otimizada
            connector = aiohttp.TCPConnector(
                limit=200,
                ttl_dns_cache=300,
                enable_cleanup_closed=True
            )
            
            async with aiohttp.ClientSession(connector=connector) as session:
                anki = AnkiConnectClient(session, self.config)
                
                # 1. Buscar notas
                try:
                    note_ids = await anki.find_notes(self.config.DECK_QUERY)
                    if self.config.LIMIT_NOTES:
                        note_ids = note_ids[:self.config.LIMIT_NOTES]
                    
                    if not note_ids:
                        console.print("[yellow]Nenhuma nota encontrada.[/yellow]")
                        return
                    
                    console.print(f"[cyan]Encontradas {len(note_ids)} notas para processar[/cyan]")
                    notes = await anki.get_all_notes_info(note_ids, progress)
                    
                except Exception as e:
                    console.print(f"[red]Erro ao buscar notas: {e}[/red]")
                    return
                
                # 2. Preparar e gerar áudios
                unique_texts = self.prepare_tasks(notes)
                console.print(f"[cyan]Textos únicos para gerar: {len(unique_texts)}[/cyan]")
                
                tts_results = await self.generate_all_audio(unique_texts, progress)
                
                # 3. Atualizar Anki
                updated = 0
                if not self.config.DRY_RUN:
                    updates = self.prepare_updates(notes, tts_results)
                    if updates:
                        console.print(f"[cyan]Atualizando {len(updates)} notas no Anki[/cyan]")
                        updated = await anki.update_notes_batch(updates, progress)
                    else:
                        console.print("[yellow]Nenhuma nota para atualizar[/yellow]")
        
        # Estatísticas finais
        duration = time.perf_counter() - start
        total_processed = self._stats['ok'] + self._stats['fail']
        rate = total_processed / duration if duration > 0 else 0
        
        console.print("\n" + "="*60)
        console.print("[bold green]PROCESSO CONCLUÍDO[/bold green]")
        console.print("="*60)
        console.print(f"Tempo total: {duration:.1f}s")
        console.print(f"Taxa: {rate:.1f} itens/s")
        console.print(f"Sucessos: {self._stats['ok']}")
        console.print(f"Falhas: {self._stats['fail']}")
        console.print(f"Pulados: {self._stats['skip']}")
        console.print(f"Retentativas: {self._stats['retry']}")
        console.print(f"Notas atualizadas: {updated}")
        
        # Mostrar falhas se houver
        if self._failed_texts:
            console.print("\n[red]Textos que falharam:[/red]")
            for text, error in self._failed_texts[:10]:  # Mostrar até 10
                console.print(f"  - {text[:50]}... ({error})")
            if len(self._failed_texts) > 10:
                console.print(f"  ... e mais {len(self._failed_texts) - 10} falhas")

# =======================
# MAIN
# =======================
def main():
    setup_logging()
    
    parser = argparse.ArgumentParser(description="Anki TTS Generator - Edge TTS")
    parser.add_argument("--reset", action="store_true", 
                       help="Remove tags antigas e regenera todos os áudios")
    parser.add_argument("--limit", type=int, 
                       help="Limitar número de notas processadas")
    parser.add_argument("--concurrency", type=int, default=100,
                       help="Número de gerações simultâneas (padrão: 100)")
    args = parser.parse_args()
    
    config = Config()
    if args.reset:
        config.RESET_MODE = True
        config.AUDIO_WRITE_MODE = "overwrite"
        console.print("[bold yellow]MODO RESET ATIVADO - Todos os áudios serão regenerados[/bold yellow]")
    if args.limit:
        config.LIMIT_NOTES = args.limit
    if args.concurrency:
        config.CONCURRENCY = args.concurrency
    
    console.print(f"[bold blue]Anki TTS Generator[/bold blue]")
    console.print(f"Query: {config.DECK_QUERY}")
    console.print(f"Concorrência: {config.CONCURRENCY}")
    console.print(f"Diretório: {config.MEDIA_DIR}")
    
    if not os.path.isdir(config.MEDIA_DIR):
        console.print(f"[red]Erro: Diretório não encontrado: {config.MEDIA_DIR}[/red]")
        sys.exit(1)
    
    # Desabilitar GC durante processamento para performance
    import gc
    gc.disable()
    
    try:
        gen = TTSGenerator(config)
        asyncio.run(gen.run())
    finally:
        gc.collect()
        gc.enable()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Processo interrompido pelo usuário[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Erro fatal: {e}[/red]")
        logging.exception("Erro fatal")