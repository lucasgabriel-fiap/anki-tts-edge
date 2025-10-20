# Anki TTS Edge

Gerador de áudio automático para cartões do Anki em português brasileiro. Processa milhares de cartões em minutos e converte LaTeX para fala natural.

## Características principais

- **Vozes brasileiras naturais** selecionadas aleatoriamente para cada áudio
- **Velocidade ajustável** (padrão: 4x mais rápido)
- **Totalmente automático** após configuração inicial
- Não requer extensões além do AnkiConnect
- **Conversão inteligente de LaTeX** e símbolos matemáticos

## Resumo

Este programa conecta no Anki via AnkiConnect, extrai o texto dos seus cartões, gera arquivos de áudio usando Edge TTS da Microsoft e adiciona as tags de som automaticamente.

**Diferencial principal:** Converte fórmulas matemáticas (LaTeX/MathML) para português falado. Se você estuda exatas, medicina ou ciências, isso economiza horas de trabalho manual.

O programa alterna automaticamente entre 5 vozes brasileiras de alta qualidade durante a geração, criando variedade natural nos áudios.

## Performance

- **2.000 cartões** processados em aproximadamente **3 minutos**
- **10.000 cartões** em cerca de **15 minutos**
- Processamento paralelo (padrão: 100 requisições simultâneas)
- Taxa de sucesso acima de **99%** com sistema de retry automático

## Funcionalidades

### Conversão de LaTeX para fala

O programa interpreta notação matemática e converte para português natural:
```latex
$x^2 + 3x - 5 = 0$
```
Gera áudio: "xis ao quadrado mais três xis menos cinco igual a zero"
```latex
\frac{dy}{dx} = 2x
```
Gera áudio: "dê i psilon sobre dê xis igual a dois xis"
```latex
\int_0^{\infty} e^{-x} dx
```
Gera áudio: "integral de zero a infinito de e elevado a menos xis dê xis"

### Símbolos e notações especiais

- **Letras gregas:** α, β, γ, Δ, Σ, Ω
- **Operadores:** ∫, ∑, ∏, √, ∞
- **Relações:** ≤, ≥, ≠, ≈, ∈, ⊂
- **Subscritos e sobrescritos:** H₂O, x², 10³

### Normalização automática

**Moedas:**

- `R$ 1.250,50` → "mil duzentos e cinquenta reais e cinquenta centavos"
- `US$ 99.99` → "noventa e nove dólares e noventa e nove centavos"

**Unidades de medida:**

- `10 km` → "dez quilômetros"
- `5 m²` → "cinco metros quadrados"
- `100 mg` → "cem miligramas"

**Números e proporções:**

- `3,14159` → "três vírgula catorze mil cento e cinquenta e nove"
- `3:2` → "três para dois"
- `1.5e-3` → "um ponto cinco vezes dez elevado a menos três"

## Vozes disponíveis

O programa seleciona aleatoriamente entre 5 vozes brasileiras naturais da Microsoft:

- **ThalitaMultilingualNeural** — Voz feminina clara e versátil
- **AntonioNeural** — Voz masculina natural
- **FranciscaNeural** — Voz feminina expressiva
- **DuarteNeural** — Voz masculina (português de Portugal)
- **RaquelNeural** — Voz feminina (português de Portugal)

Cada áudio recebe uma voz diferente, criando variedade natural no deck.

## Requisitos

- Python 3.8+
- Anki 2.1+
- AnkiConnect (add-on código: **2055492159**)
- Conexão com internet (Edge TTS requer acesso à API da Microsoft)
- Compatível com Windows, macOS e Linux

## Instalação

### 1. Instalar AnkiConnect

No Anki:

1. Ferramentas → Complementos → Obter Complementos
2. Cole o código: `2055492159`
3. Reinicie o Anki

### 2. Instalar dependências
```bash
pip install edge-tts aiohttp rich
```

### 3. Baixar arquivos

Clone o repositório ou baixe os arquivos `main_script.py` e `converters.py`:
```bash
git clone https://github.com/seu-usuario/anki-tts-edge.git
cd anki-tts-edge
```

## Configuração

Edite `main_script.py` e ajuste as seguintes variáveis na classe `Config`:

### 1. Deck alvo
```python
DECK_QUERY: str = 'deck:"NomeDoSeuDeck"'
```

Substitua "NomeDoSeuDeck" pelo nome exato do seu deck. Exemplos:
```python
DECK_QUERY: str = 'deck:"Matemática"'
DECK_QUERY: str = 'deck:"Medicina::Anatomia"'
DECK_QUERY: str = 'deck:"Português::Vocabulário"'
```

### 2. Diretório de mídia
```python
MEDIA_DIR: str = r"C:\Users\SeuUsuario\AppData\Roaming\Anki2\Usuario 1\collection.media"
```

Como encontrar o caminho correto:

1. Abra o Anki
2. Ferramentas → Preferências → Mostrar Pasta
3. Entre na pasta do seu perfil (geralmente "Usuario 1" ou "User 1")
4. Navegue até `collection.media`
5. Copie o caminho completo

Exemplos por sistema operacional:
```python
# Windows
MEDIA_DIR: str = r"C:\Users\SeuNome\AppData\Roaming\Anki2\Usuario 1\collection.media"

# macOS
MEDIA_DIR: str = "/Users/SeuNome/Library/Application Support/Anki2/User 1/collection.media"

# Linux
MEDIA_DIR: str = "/home/seunome/.local/share/Anki2/User 1/collection.media"
```

**Importante:** No Windows, mantenha o `r` antes das aspas.

### 3. Campos (opcional)

Por padrão, o programa processa os campos "Frente" e "Verso":
```python
FIELDS_TO_PROCESS: List[str] = field(default_factory=lambda: ["Frente", "Verso"])
```

Ajuste conforme a nomenclatura dos seus cartões. Exemplos:
```python
FIELDS_TO_PROCESS: List[str] = field(default_factory=lambda: ["Palavra", "Definição"])
FIELDS_TO_PROCESS: List[str] = field(default_factory=lambda: ["Front", "Back"])
FIELDS_TO_PROCESS: List[str] = field(default_factory=lambda: ["Pergunta", "Resposta"])
```

## Uso

### Execução básica

Com o Anki aberto, execute:
```bash
python main_script.py
```

O programa irá:

1. Conectar no Anki via AnkiConnect
2. Buscar cartões do deck especificado
3. Gerar arquivos MP3 na pasta de mídia
4. Inserir tags `[sound:arquivo.mp3]` nos campos
5. Exibir progresso em tempo real

### Opções de linha de comando

**Testar com poucos cartões:**
```bash
python main_script.py --limit 10
```

**Regenerar todos os áudios:**
```bash
python main_script.py --reset
```

Remove áudios existentes e gera novamente.

**Ajustar concorrência:**
```bash
python main_script.py --concurrency 50  # Mais conservador
python main_script.py --concurrency 200 # Mais agressivo
```

## Personalização

### Velocidade da fala

Por padrão, os áudios são gerados 4x mais rápidos que o normal. Para ajustar:
```python
EDGE_TTS_RATE: str = "+400%"
```

Valores comuns:

- `"+0%"` — Velocidade normal
- `"+200%"` — 2x mais rápido
- `"+400%"` — 4x mais rápido (padrão)
- `"+600%"` — 6x mais rápido

### Ordem de preferência das vozes

Para alterar a ordem de seleção das vozes:
```python
EDGE_TTS_VOICES: List[str] = field(default_factory=lambda: [
    "pt-BR-ThalitaMultilingualNeural",  # Será mais usada
    "pt-BR-AntonioNeural",
    "pt-BR-FranciscaNeural",
    "pt-PT-DuarteNeural",
    "pt-PT-RaquelNeural",  # Será menos usada
])
```

A primeira voz da lista tem prioridade, mas todas serão usadas aleatoriamente.

### Timeouts e retries
```python
EDGE_TTS_TIMEOUT_S: int = 60      # Timeout por requisição
EDGE_TTS_MAX_RETRIES: int = 3     # Tentativas antes de falhar
CONCURRENCY: int = 100             # Requisições paralelas
```

## Resolução de problemas

### Erro de conexão com Anki

**Causa:** AnkiConnect não está instalado ou Anki está fechado.

**Solução:**

1. Verifique se o Anki está aberto
2. Confirme que AnkiConnect (código 2055492159) está instalado
3. Reinicie o Anki

### Falhas na geração de áudio

**Causa:** Instabilidade de rede ou sobrecarga.

**Solução:**

1. Execute o programa novamente (processa apenas o que faltou)
2. Reduza a concorrência: `--concurrency 50`
3. Verifique sua conexão com internet

### Diretório de mídia não encontrado

**Causa:** Caminho incorreto em `MEDIA_DIR`.

**Solução:**

1. Confirme o caminho seguindo as instruções da seção Configuração
2. No Windows, use `r` antes das aspas: `r"C:\..."`
3. Verifique se o caminho termina em `collection.media`

### Performance lenta

**Causa:** Concorrência baixa ou limitações de rede.

**Solução:**

1. Aumente a concorrência: `--concurrency 150`
2. Feche programas que consomem banda
3. Execute em horários de menor congestionamento

### Cartões sem áudio continuam sem áudio

**Causa:** O campo pode estar vazio ou ter menos caracteres que o mínimo.

**Solução:**

1. Verifique se os campos especificados em `FIELDS_TO_PROCESS` existem nos seus cartões
2. Confira se há texto nos campos (mínimo padrão: 1 caractere)
3. Use `--reset` para forçar regeneração

## Arquitetura técnica

### Fluxo de processamento

1. **Busca de notas:** AnkiConnect retorna IDs e campos via API REST
2. **Extração de texto:** HTML é stripped, LaTeX/MathML convertido para texto
3. **Deduplicação:** Textos idênticos geram apenas um áudio
4. **Geração paralela:** edge-tts processa múltiplos textos simultaneamente
5. **Verificação:** Arquivos são validados (tamanho mínimo 1KB)
6. **Atualização:** Tags `[sound:...]` são inseridas via AnkiConnect

### Conversão LaTeX

O módulo `converters.py` implementa:

- Parser manual de comandos LaTeX (não usa bibliotecas externas)
- Mapeamento de ~200 comandos matemáticos para português
- Tratamento de frações, raízes, limites, integrais, somatórios
- Conversão de MathML via ElementTree
- Cache LRU para performance

### Robustez

- Sistema de retry com backoff exponencial
- Rotação automática entre vozes em caso de falha
- Validação de integridade dos arquivos gerados
- Logs detalhados em `tts_errors.log`

## Limitações conhecidas

- **Idioma:** Apenas português brasileiro no momento
- **Conexão:** Requer internet (Edge TTS é serviço online)
- **Precisão matemática:** Notações muito complexas podem ter conversão imperfeita


MIT License - Uso livre para fins pessoais e comerciais.

## Créditos

Dependências:

- **edge-tts** - Interface Python para Microsoft Edge TTS
- **aiohttp** - Cliente HTTP assíncrono
- **rich** - Formatação de terminal

---

**Versão:** 1.0.0  
**Atualização:** Outubro 2025