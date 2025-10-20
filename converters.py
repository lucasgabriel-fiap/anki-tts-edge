# -*- coding: utf-8 -*-
"""
Módulo de constantes e funções para conversão de texto.
Contém toda a lógica para limpar HTML, converter LaTeX/MathML para fala
e normalizar unidades, moedas e números para o português brasileiro.
"""

import re
import html
import unicodedata
import xml.etree.ElementTree as ET
from functools import lru_cache
from typing import Set

# =======================
# Helpers
# =======================
def safe_unescape(x: str, times: int = 3) -> str:
    for _ in range(times):
        old = x
        x = html.unescape(x)
        if x == old:
            break
    return x

def balanced_span(s: str, i: int, open_char="{", close_char="}"):
    """
    Retorna (start, end_exclusive) do bloco balanceado iniciando em s[i] == open_char.
    Se falhar, retorna None.
    """
    if i >= len(s) or s[i] != open_char:
        return None
    depth = 0
    for j in range(i, len(s)):
        if s[j] == open_char:
            depth += 1
        elif s[j] == close_char:
            depth -= 1
            if depth == 0:
                return (i, j + 1)
    return None

def strip_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

# =======================
# Regex Pool Expandido com Foco em Legibilidade
# =======================
class RegexPool:
    """Pool de regex compilados para reutilização e legibilidade perfeita"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._compile_all()
        return cls._instance
    
    def _compile_all(self):
        # Math patterns
        self.DOLLAR2 = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
        self.DOLLAR1 = re.compile(r"(?<!\\)\$(.+?)(?<!\\)\$", re.DOTALL)
        self.PAREN = re.compile(r"\\\((.+?)\\\)", re.DOTALL)
        self.BRACK = re.compile(r"\\\[(.+?)\\\]", re.DOTALL)
        self.ANKI = re.compile(r"<anki-mathjax[^>]*>(.*?)</anki-mathjax>", re.IGNORECASE | re.DOTALL)
        self.MJSCRIPT = re.compile(r'<script[^>]+type=["\']math/(?:tex|tex;?\s*mode=display)["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
        self.MATHML = re.compile(r"<math\b[^>]*>.*?</math>", re.IGNORECASE | re.DOTALL)
        
        # HTML patterns
        self.HTML_SUB = re.compile(r"([A-Za-z0-9])\s*<\s*sub\s*>\s*([^<]+?)\s*<\s*/\s*sub\s*>", re.IGNORECASE)
        self.HTML_SUP = re.compile(r"([A-Za-z0-9])\s*<\s*sup\s*>\s*([^<]+?)\s*<\s*/\s*sup\s*>", re.IGNORECASE)
        self.NOBR_BEFORE_MATH = re.compile(r"<\s*nobr\s*>.*?<\s*/\s*nobr\s*>\s*(?=<\s*math\b)", re.IGNORECASE | re.DOTALL)
        
        # Tags HTML que devem ser completamente removidas
        self.STRONG_TAG = re.compile(r"<\s*/?strong\s*>", re.IGNORECASE)
        self.EM_TAG = re.compile(r"<\s*/?em\s*>", re.IGNORECASE)
        self.U_TAG = re.compile(r"<\s*/?u\s*>", re.IGNORECASE)
        self.B_TAG = re.compile(r"<\s*/?b\s*>", re.IGNORECASE)
        self.I_TAG = re.compile(r"<\s*/?i\s*>", re.IGNORECASE)
        self.STRIKE_TAG = re.compile(r"<\s*/?(?:strike|s|del)\s*>", re.IGNORECASE)
        self.MARK_TAG = re.compile(r"<\s*/?mark\s*>", re.IGNORECASE)
        self.CODE_TAG = re.compile(r"<\s*/?code\s*>", re.IGNORECASE)
        self.LI_TAG = re.compile(r"<\s*/?li\s*>", re.IGNORECASE)
        self.OL_UL_TAG = re.compile(r"<\s*/?[ou]l\s*>", re.IGNORECASE)
        
        # LaTeX commands
        self.KEEP_ARG = re.compile(r"""\\(?:text[a-zA-Z]*|textrm|textit|textbf|mathrm|mathbf|mathit|mathsf|operatorname)\s*\{([^{}]*)\}""", re.VERBOSE)
        self.DROP_COMMANDS = re.compile(r"""\\(?:left|right|big|Big|bigg|Bigg|middle|,|;|!|quad|qquad|displaystyle|textstyle|scriptstyle|scriptscriptstyle|hspace|vspace|phantom|mathstrut)\b""", re.VERBOSE)
        
        # Unidades e potências
        self.UNIT_POWER = re.compile(r"(\b\w+)\^(\-?\d+)")
        self.UNIT_UNDERSCORE = re.compile(r"(\b\w+)_(\d+)")
        
        # Currency and numbers
        self.CURRENCY_BRL = re.compile(r"(?i)R(?:[\s\u00A0\u202F\u2007\n])*\\?\$(?:[\s\u00A0\u202F\u2007\n])*(?P<amount>(?:\d{1,3}(?:\.\d{3})*|\d+)(?:,\d+)?)")
        self.CURRENCY_USD = re.compile(r"(?i)US?\s*\\?\$\s*(?P<amount>(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?)")
        self.NUM_COLON_NUM = re.compile(r"(?<!\w)(\d+(?:[.,]\d+)?)\s*:\s*(\d+(?:[.,]\d+)?)(?!\w)")
        self.E_NOTATION = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*[eE]\s*([+-]?\d+)\b")
        
        # HTML stripping
        self.BLOCK_TAG = re.compile(r"(?is)<(script|style|head|title|meta|noscript|template)[^>]*>.*?</\1>")
        self.BR_CLOSERS = re.compile(r"(?i)</\s*(p|div|li|tr|td|th|h[1-6]|section|article|nav|aside|footer|header)\s*>")
        self.BR_OPENERS = re.compile(r"(?i)<\s*(p|div|li|tr|td|th|h[1-6]|section|article|nav|aside|footer|header)[^>]*>")
        self.BR_TAG = re.compile(r"(?i)<\s*br\s*/?\s*>")
        self.HR_TAG = re.compile(r"(?i)<\s*hr\s*/?\s*>")
        self.TAG_ANY = re.compile(r"(?is)<[^>]+>")
        self.HTML_COM = re.compile(r"(?s)")
        
        # Special characters and escapes
        self.BACKSLASH_ESCAPES = re.compile(r"\\([\\{}_$&#%])")
        self.LATEX_BACKSLASH = re.compile(r"\\\\")
        self.MULTIPLE_SPACES = re.compile(r"\s{2,}")
        self.MULTIPLE_DOTS = re.compile(r"\.{4,}")
        
        # Other patterns
        self.SOUND_TAG = re.compile(r"\[sound:([^\]]+)\]", re.IGNORECASE)
        self.URL_PAT = re.compile(r"(https?://\S+|www\.\S+)", re.IGNORECASE)
        self.EMAIL_PAT = re.compile(r"\b[\w\.-]+@[\w\.-]+\.\w+\b")
        self.WINPATH_PAT = re.compile(r"\b[A-Za-z]:\\[^\s]+")
        
        # Números decimais e separadores
        self.DECIMAL_COMMA = re.compile(r"(\d+),(\d+)")
        # Pontos de milhar no padrão BR (ex.: 1.234.567
        self.THOUSAND_DOT = re.compile(r"\b\d{1,3}(?:\.\d{3})+(?!\d)")

# Singleton instance
regex = RegexPool()

# =======================
# Dicionários de Conversão Expandidos
# =======================

# Comandos LaTeX para fala - expandido
LATEX_CMD_MAP = {
    # Operações básicas
    r"\cdot": " vezes ", r"\times": " vezes ", r"\div": " dividido por ",
    r"\pm": " mais ou menos ", r"\mp": " menos ou mais ",
    r"\oplus": " mais ", r"\ominus": " menos ", r"\otimes": " vezes ",
    r"\oslash": " dividido por ", r"\odot": " vezes ", r"\star": " estrela ",
    r"\ast": " asterisco ", r"\circ": " círculo ", r"\bullet": " ponto ", r"\cdots": " reticências ",
    r"\ldots": " reticências ", r"\vdots": " reticências verticais ", r"\ddots": " reticências diagonais ",
    
    # Comparações
    r"\leq": " menor ou igual a ", r"\geq": " maior ou igual a ",
    r"\le": " menor ou igual a ", r"\ge": " maior ou igual a ",
    r"\lt": " menor que ", r"\gt": " maior que ",
    r"\ll": " muito menor que ", r"\gg": " muito maior que ",
    r"\neq": " diferente de ", r"\ne": " diferente de ",
    r"\approx": " aproximadamente ", r"\sim": " semelhante a ",
    r"\simeq": " aproximadamente igual a ", r"\cong": " congruente a ",
    r"\equiv": " equivalente a ", r"\propto": " proporcional a ",
    
    # Setas
    r"\to": " tende a ", r"\rightarrow": " tende a ",
    r"\leftarrow": " vem de ", r"\leftrightarrow": " se e somente se ",
    r"\Rightarrow": " implica ", r"\Leftarrow": " é implicado por ",
    r"\Leftrightarrow": " se e somente se ", r"\mapsto": " mapeia para ",
    r"\uparrow": " cresce ", r"\downarrow": " decresce ",
    
    # Conjuntos
    r"\in": " pertence a ", r"\notin": " não pertence a ",
    r"\subset": " está contido em ", r"\supset": " contém ",
    r"\subseteq": " está contido ou é igual a ", r"\supseteq": " contém ou é igual a ",
    r"\cup": " união ", r"\cap": " interseção ",
    r"\emptyset": " conjunto vazio ", r"\varnothing": " conjunto vazio ",
    r"\setminus": " menos ", r"\complement": " complemento ",
    
    # Lógica
    r"\land": " e ", r"\wedge": " e ", r"\lor": " ou ", r"\vee": " ou ",
    r"\neg": " não ", r"\lnot": " não ", r"\forall": " para todo ",
    r"\exists": " existe ", r"\nexists": " não existe ",
    r"\therefore": " portanto ", r"\because": " porque ",
    
    # Funções matemáticas
    r"\sqrt": " raiz quadrada de ", r"\cbrt": " raiz cúbica de ",
    r"\log": " logaritmo ", r"\ln": " logaritmo natural ",
    r"\lg": " logaritmo na base 10 ", r"\exp": " exponencial ",
    r"\sin": " seno ", r"\cos": " cosseno ", r"\tan": " tangente ",
    r"\sec": " secante ", r"\csc": " cossecante ", r"\cot": " cotangente ",
    r"\arcsin": " arco seno ", r"\arccos": " arco cosseno ", r"\arctan": " arco tangente ",
    r"\sinh": " seno hiperbólico ", r"\cosh": " cosseno hiperbólico ", r"\tanh": " tangente hiperbólica ",
    r"\det": " determinante ", r"\dim": " dimensão ", r"\ker": " núcleo ",
    r"\rank": " posto ", r"\trace": " traço ", r"\deg": " grau ",
    
    # Cálculo e limites
    r"\lim": " limite ", r"\sum": " somatório ", r"\prod": " produtório ",
    r"\int": " integral ", r"\iint": " integral dupla ", r"\iiint": " integral tripla ",
    r"\oint": " integral de linha ", r"\partial": " parcial ",
    r"\nabla": " nabla ", r"\grad": " gradiente ", r"\curl": " rotacional ",
    
    # Letras gregas
    r"\alpha": " alfa ", r"\beta": " beta ", r"\gamma": " gama ",
    r"\delta": " delta ", r"\epsilon": " épsilon ", r"\varepsilon": " épsilon ",
    r"\zeta": " zeta ", r"\eta": " eta ", r"\theta": " teta ",
    r"\vartheta": " teta ", r"\iota": " iota ", r"\kappa": " kappa ",
    r"\lambda": " lambda ", r"\mu": " mi ", r"\nu": " ni ",
    r"\xi": " csi ", r"\pi": " pi ", r"\varpi": " pi ",
    r"\rho": " rô ", r"\varrho": " rô ", r"\sigma": " sigma ",
    r"\varsigma": " sigma ", r"\tau": " tau ", r"\upsilon": " úpsilon ",
    r"\phi": " fi ", r"\varphi": " fi ", r"\chi": " qui ",
    r"\psi": " psi ", r"\omega": " ômega ",
    
    # Letras gregas maiúsculas
    r"\Gamma": " gama maiúsculo ", r"\Delta": " delta maiúsculo ",
    r"\Theta": " teta maiúsculo ", r"\Lambda": " lambda maiúsculo ",
    r"\Xi": " csi maiúsculo ", r"\Pi": " pi maiúsculo ",
    r"\Sigma": " sigma maiúsculo ", r"\Upsilon": " úpsilon maiúsculo ",
    r"\Phi": " fi maiúsculo ", r"\Psi": " psi maiúsculo ",
    r"\Omega": " ômega maiúsculo ",
    
    # Outros símbolos
    r"\infty": " infinito ", r"\aleph": " alef ", r"\beth": " bet ",
    r"\gimel": " guimel ", r"\daleth": " dalet ",
    r"\hbar": " h barra ", r"\ell": " ele ", r"\wp": " p de weierstrass ",
    r"\Re": " parte real ", r"\Im": " parte imaginária ",
    r"\prime": " linha ", r"\backprime": " linha reversa ",
    r"\top": " topo ", r"\bot": " base ", r"\angle": " ângulo ",
    r"\triangle": " triângulo ", r"\square": " quadrado ",
    r"\diamond": " losango ",
    
    # Delimitadores
    r"\langle": " abre ", r"\rangle": " fecha ",
    r"\lceil": " teto abre ", r"\rceil": " teto fecha ",
    r"\lfloor": " piso abre ", r"\rfloor": " piso fecha ",
    r"\|": " barra vertical ", r"\Vert": " barra dupla ",
    
    # Extras úteis
    r"\mod": " módulo ", r"\bmod": " módulo ", r"\pmod": " módulo ",
}

# Mapa de caracteres Unicode - expandido
UNICODE_MAP = {
    # Operadores matemáticos
    "≤": " menor ou igual a ", "≥": " maior ou igual a ", "≠": " diferente de ",
    "≈": " aproximadamente ", "≡": " equivalente a ", "≢": " não equivalente a ",
    "∼": " semelhante a ", "≃": " assintoticamente igual a ", "≅": " aproximadamente igual a ",
    "∝": " proporcional a ", "∞": " infinito ", "∂": " parcial ",
    "·": " vezes ", "⋅": " vezes ", "∙": " vezes ",
    
    # Operações
    "±": " mais ou menos ", "∓": " menos ou mais ", "×": " vezes ",
    "÷": " dividido por ", "⊕": " mais ", "⊖": " menos ",
    "⊗": " vezes ", "⊘": " dividido por ", "⊙": " produto direto ",
    
    # Conjuntos
    "∈": " pertence a ", "∉": " não pertence a ", "⊂": " está contido em ",
    "⊃": " contém ", "⊆": " está contido ou igual a ", "⊇": " contém ou igual a ",
    "∪": " união ", "∩": " interseção ", "∅": " conjunto vazio ",
    "∖": " diferença ", "⊄": " não está contido ", "⊅": " não contém ",
    
    # Lógica
    "∧": " e ", "∨": " ou ", "¬": " não ", "⇒": " implica ",
    "⇐": " é implicado por ", "⇔": " se e somente se ", "∀": " para todo ",
    "∃": " existe ", "∄": " não existe ", "∴": " portanto ", "∵": " porque ",
    
    # Setas
    "→": " tende a ", "←": " vem de ", "↑": " cresce ", "↓": " decresce ",
    "↔": " bidirecional ", "⇄": " reversível ", "↦": " mapeia para ",
    
    # Integrais e somatórios
    "∫": " integral ", "∬": " integral dupla ", "∭": " integral tripla ",
    "∮": " integral de linha ", "∑": " somatório ", "∏": " produtório ",
    
    # Outros símbolos matemáticos
    "√": " raiz quadrada ", "∛": " raiz cúbica ", "∜": " raiz quarta ",
    "∇": " nabla ", "∆": " delta ", "∂": " derivada parcial ",
    "|": " barra vertical ", "‖": " barra dupla ",
    
    # Letras gregas
    "α": " alfa ", "β": " beta ", "γ": " gama ", "δ": " delta ",
    "ε": " épsilon ", "ζ": " zeta ", "η": " eta ", "θ": " teta ",
    "ι": " iota ", "κ": " kappa ", "λ": " lambda ", "μ": " mi ",
    "ν": " ni ", "ξ": " csi ", "π": " pi ", "ρ": " rô ",
    "σ": " sigma ", "τ": " tau ", "υ": " úpsilon ", "φ": " fi ",
    "χ": " qui ", "ψ": " psi ", "ω": " ômega ",
    "Α": " alfa maiúsculo ", "Β": " beta maiúsculo ", "Γ": " gama maiúsculo ",
    "Δ": " delta maiúsculo ", "Ε": " épsilon maiúsculo ", "Ζ": " zeta maiúsculo ",
    "Η": " eta maiúsculo ", "Θ": " teta maiúsculo ", "Ι": " iota maiúsculo ",
    "Κ": " kappa maiúsculo ", "Λ": " lambda maiúsculo ", "Μ": " mi maiúsculo ",
    "Ν": " ni maiúsculo ", "Ξ": " csi maiúsculo ", "Π": " pi maiúsculo ",
    "Ρ": " rô maiúsculo ", "Σ": " sigma maiúsculo ", "Τ": " tau maiúsculo ",
    "Υ": " úpsilon maiúsculo ", "Φ": " fi maiúsculo ", "Χ": " qui maiúsculo ",
    "Ψ": " psi maiúsculo ", "Ω": " ômega maiúsculo ",
    
    # Superscripts e subscripts comuns
    "²": " ao quadrado ", "³": " ao cubo ", "⁴": " à quarta ",
    "⁵": " à quinta ", "⁶": " à sexta ", "⁷": " à sétima ",
    "⁸": " à oitava ", "⁹": " à nona ", "⁰": " à zero ",
    "⁺": " mais ", "⁻": " menos ", "⁼": " igual ", "⁽": " abre parênteses ",
    "⁾": " fecha parênteses ", "ⁿ": " à n ",
    "₀": " zero ", "₁": " um ", "₂": " dois ", "₃": " três ",
    "₄": " quatro ", "₅": " cinco ", "₆": " seis ", "₇": " sete ",
    "₈": " oito ", "₉": " nove ", "₊": " mais ", "₋": " menos ",
    "₌": " igual ", "₍": " abre ", "₎": " fecha ",
    
    # Frações
    "½": " um meio ", "⅓": " um terço ", "⅔": " dois terços ",
    "¼": " um quarto ", "¾": " três quartos ", "⅕": " um quinto ",
    "⅖": " dois quintos ", "⅗": " três quintos ", "⅘": " quatro quintos ",
    "⅙": " um sexto ", "⅚": " cinco sextos ", "⅐": " um sétimo ",
    "⅛": " um oitavo ", "⅜": " três oitavos ", "⅝": " cinco oitavos ",
    "⅞": " sete oitavos ", "⅑": " um nono ", "⅒": " um décimo ",
    
    # Moedas
    "€": " euros ", "£": " libras ", "¥": " ienes ", "¢": " centavos ",
    "₹": " rúpias ", "₽": " rublos ", "₩": " wons ", "₪": " shekels ",
    "₦": " nairas ", "₨": " rúpias ", "₱": " pesos ", "₴": " hryvnias ",
    
    # Outros símbolos
    "°": " graus ", "℃": " graus celsius ", "℉": " graus fahrenheit ",
    "№": " número ", "™": " marca registrada ", "®": " registrado ",
    "©": " copyright ", "§": " seção ", "¶": " parágrafo ",
    "†": " adaga ", "‡": " adaga dupla ", "•": " ponto ",
    "…": " reticências ", "‰": " por mil ", "′": " linha ",
    "″": " duas linhas ", "‴": " três linhas ", "⁗": " quatro linhas ",
}

# =======================
# Unidades de medida — REVISADO p/ legibilidade
# =======================

# Tokens de 1 letra que NÃO devemos expandir nunca
BLOCKED_UNIT_TOKENS: Set[str] = {"A", "a", "B"}

UNIT_MAP = {
    # Comprimento
    "km": "quilômetros", "m": "metros", "cm": "centímetros", "mm": "milímetros",
    "μm": "micrômetros", "nm": "nanômetros", "pm": "picômetros",
    "mi": "milhas", "yd": "jardas", "ft": "pés", "in": "polegadas",
    # Área
    "km²": "quilômetros quadrados", "m²": "metros quadrados", 
    "cm²": "centímetros quadrados", "mm²": "milímetros quadrados",
    # Volume
    "km³": "quilômetros cúbicos", "m³": "metros cúbicos",
    "cm³": "centímetros cúbicos", "mm³": "milímetros cúbicos",
    "L": "litros", "mL": "mililitros", "μL": "microlitros",
    "gal": "galões", "qt": "quartos", "pt": "pintas",
    # Massa
    "kg": "quilogramas", "g": "gramas", "mg": "miligramas",
    "μg": "microgramas", "ng": "nanogramas", "t": "toneladas",
    "lb": "libras", "oz": "onças",
    # Tempo (NÃO mapear 'a' → anos; removido)
    "s": "segundos", "ms": "milissegundos", "μs": "microssegundos",
    "ns": "nanossegundos", "min": "minutos", "h": "horas",
    "d": "dias", "sem": "semanas",
    # Elétrica (NÃO mapear 'A' puro → ampères; mantemos mA/μA)
    "mA": "miliampères", "μA": "microampères",
    "V": "volts", "mV": "milivolts", "kV": "quilovolts",
    "W": "watts", "mW": "miliwatts", "kW": "quilowatts", "MW": "megawatts",
    "Ω": "ohms", "kΩ": "quilo-ohms", "MΩ": "mega-ohms",
    "F": "farads", "μF": "microfarads", "nF": "nanofarads", "pF": "picofarads",
    "H": "henries", "mH": "milihenries", "μH": "microhenries",
    # Pressão
    "Pa": "pascals", "kPa": "quilopascals", "MPa": "megapascals",
    "bar": "bars", "mbar": "milibars", "atm": "atmosferas",
    "psi": "libras por polegada quadrada", "Torr": "torrs",
    # Temperatura
    "K": "kelvin", "°C": "graus celsius", "°F": "graus fahrenheit",
    # Energia
    "J": "joules", "kJ": "quilojoules", "MJ": "megajoules",
    "cal": "calorias", "kcal": "quilocalorias", "eV": "elétron-volts",
    # Frequência
    "Hz": "hertz", "kHz": "quilohertz", "MHz": "megahertz", "GHz": "gigahertz",
    # Dados (NÃO mapear 'B' puro → bytes)
    "bit": "bits", "KB": "quilobytes", "MB": "megabytes",
    "GB": "gigabytes", "TB": "terabytes", "PB": "petabytes",
    # Velocidade
    "m/s": "metros por segundo", "km/h": "quilômetros por hora",
    "mph": "milhas por hora", "ft/s": "pés por segundo",
    # Força
    "N": "newtons", "kN": "quilonewtons", "lbf": "libras-força",
    # Químicas
    "mol": "mols", "mmol": "milimols", "μmol": "micromols",
    "M": "molar", "mM": "milimolar", "μM": "micromolar",
    "pH": "pH", "pKa": "pKa", "pKb": "pKb",
}

# =======================
# Funções de Limpeza e Conversão para Legibilidade Perfeita
# =======================

def clean_latex_backslashes(text: str) -> str:
    """Remove ou substitui barras invertidas problemáticas"""
    if not text:
        return text
    text = regex.LATEX_BACKSLASH.sub(" ", text)       # remove \\ (quebras)
    text = regex.BACKSLASH_ESCAPES.sub(r"\1", text)   # \% \_ etc
    text = re.sub(r"\\(?![a-zA-Z])", " ", text)       # barras soltas
    return text

def process_units_and_powers(text: str) -> str:
    """
    Processa unidades e potências visando leitura natural, com regras de legibilidade:
    - Nunca expandir tokens ambíguos bloqueados ({"A","a","B"}).
    - Unidades de 1 letra só expandem com número antes ("10 s" → "10 segundos").
    - Unidades compostas e de 2+ caracteres seguem mapeando normalmente.
    - Expoentes com ^ usam nomes de unidade apenas se a base não for bloqueada.
    """
    if not text:
        return text
    
    # potências com ^
    def replace_power(match):
        base = match.group(1)
        exp = match.group(2)

        # Base bloqueada? Não mapear para unidade.
        if base in BLOCKED_UNIT_TOKENS:
            base_unit = base
        else:
            base_unit = base
            for unit, name in UNIT_MAP.items():
                if base == unit or base.endswith(unit):
                    if unit in BLOCKED_UNIT_TOKENS:
                        base_unit = base
                    else:
                        base_unit = name
                    break

        if exp == "2":
            return f"{base_unit} ao quadrado"
        elif exp == "3":
            return f"{base_unit} ao cubo"
        elif exp == "-1":
            return f"{base_unit} à menos um"
        elif exp == "-2":
            return f"{base_unit} à menos dois"
        elif exp.startswith("-"):
            return f"{base_unit} à menos {exp[1:]}"
        else:
            return f"{base_unit} elevado a {exp}"
    text = regex.UNIT_POWER.sub(replace_power, text)
    
    # índices com _
    def replace_underscore(match):
        base = match.group(1)
        sub = match.group(2)
        return f"{base} {sub}"
    text = regex.UNIT_UNDERSCORE.sub(replace_underscore, text)
    
    # substituição direta de unidades
    def replace_unit_tokens(t: str) -> str:
        for unit, name in sorted(UNIT_MAP.items(), key=lambda x: -len(x[0])):
            if unit in BLOCKED_UNIT_TOKENS:
                continue

            # unidades de 1 letra (apenas letras) → exigem número antes
            if len(unit) == 1 and unit.isalpha():
                pattern = rf"(?<!\w)(\d+(?:[.,]\d+)?)(?:\s*){re.escape(unit)}\b"
                t = re.sub(pattern, lambda m: f"{m.group(1)} {name}", t)
            else:
                pattern = rf"(?<!\w){re.escape(unit)}(?=\s|$|[.,;!?)])"
                t = re.sub(pattern, name, t)
        return t

    text = replace_unit_tokens(text)
    return text

def normalize_numbers(text: str) -> str:
    """Normaliza números para leitura em português com padronização"""
    if not text:
        return text
    
    # remover pontos de milhar (BR)
    def replace_thousand_dot(m):
        return m.group(0).replace(".", "")
    text = regex.THOUSAND_DOT.sub(replace_thousand_dot, text)
    
    # proporções 3:2
    def replace_ratio(match):
        n1, n2 = match.group(1), match.group(2)
        return f"{n1} para {n2}"
    text = regex.NUM_COLON_NUM.sub(replace_ratio, text)
    
    # notação científica 1e-3
    def replace_enotation(m):
        base, expo = m.group(1), m.group(2)
        base = base.replace(",", " vírgula ").replace(".", " ponto ")
        sign = "menos " if expo.startswith("-") else ""
        e = expo.lstrip("+-")
        return f"{base} vezes dez elevado a {sign}{e}"
    text = regex.E_NOTATION.sub(replace_enotation, text)
    
    # vírgula decimal -> “vírgula”
    def replace_decimal_comma(m):
        return f"{m.group(1)} vírgula {m.group(2)}"
    text = regex.DECIMAL_COMMA.sub(replace_decimal_comma, text)
    
    return text

def normalize_currency(text: str) -> str:
    """Converte moedas para formato falado com plural/singular corretos e fallback para 'R$'."""
    if not text:
        return text

    def _plural_pt(value_str: str, singular: str, plural: str) -> str:
        try:
            v = int(value_str)
        except ValueError:
            v = 2 if value_str != "1" else 1
        return singular if v == 1 else plural

    # BRL: R$ 1.234,56
    def format_brl(match):
        amount = match.group('amount').replace(".", "")
        if "," in amount:
            reais, centavos = amount.split(",")
            reais_word = _plural_pt(reais or "0", "real", "reais")
            cent_word  = _plural_pt(centavos or "0", "centavo", "centavos")
            if centavos == "00" or centavos == "":
                return f"{reais} {reais_word}"
            elif reais == "" or reais == "0":
                return f"{centavos} {cent_word}"
            else:
                return f"{reais} {reais_word} e {centavos} {cent_word}"
        else:
            reais_word = _plural_pt(amount or "0", "real", "reais")
            return f"{amount} {reais_word}"

    brl_pattern_robust = re.compile(
        r"(?i)\bR(?:[\s\u00A0\u202F\u2007\n])*\\?\$?\s*"
        r"(?P<amount>(?:\d{1,3}(?:\.\d{3})*|\d+)(?:,\d+)?)\b"
    )
    text = brl_pattern_robust.sub(format_brl, text)

    # USD: US$ 1,234.56
    def format_usd(match):
        amount = match.group('amount').replace(",", "")
        if "." in amount:
            dollars, cents = amount.split(".")
            dol_word  = _plural_pt(dollars or "0", "dólar", "dólares")
            cent_word = _plural_pt(cents or "0", "centavo", "centavos")
            if cents == "00" or cents == "":
                return f"{dollars} {dol_word}"
            elif dollars == "" or dollars == "0":
                return f"{cents} {cent_word}"
            else:
                return f"{dollars} {dol_word} e {cents} {cent_word}"
        else:
            dol_word = _plural_pt(amount or "0", "dólar", "dólares")
            return f"{amount} {dol_word}"

    text = regex.CURRENCY_USD.sub(format_usd, text)

    text = re.sub(r"(?i)R\s*\\?\$", "reais", text)
    text = text.replace("€", " euros ").replace("£", " libras ").replace("¥", " ienes ")
    return text

# =======================
# Conversor MathML -> Fala
# =======================
def mathml_to_text(xml_str: str) -> str:
    try:
        root = ET.fromstring(xml_str)
    except Exception:
        return strip_ws(re.sub(r"<[^>]+>", " ", xml_str))
    
    def mo_text(s):
        s = s.strip()
        return UNICODE_MAP.get(s, s)
    
    def visit(node) -> str:
        tag = node.tag.split("}")[-1].lower()
        if tag in ("mi", "mn"):
            return strip_ws("".join(node.itertext()))
        if tag == "mo":
            return strip_ws(mo_text("".join(node.itertext())))
        if tag == "mtext":
            return strip_ws("".join(node.itertext()))
        if tag == "msup":
            children = list(node)
            if len(children) == 2:
                base = visit(children[0])
                exp  = visit(children[1])
                if exp in ("T", "t"):
                    return f"{base} transposto"
                if exp in ("2", "³", "3"):
                    if exp in ("2",):
                        return f"{base} ao quadrado"
                    if exp in ("3","³"):
                        return f"{base} ao cubo"
                return f"{base} elevado a {exp}"
        if tag == "msub":
            children = list(node)
            if len(children) == 2:
                base = visit(children[0])
                sub  = visit(children[1])
                return f"{base} {sub}"
        if tag == "msubsup":
            children = list(node)
            if len(children) == 3:
                base = visit(children[0])
                sub  = visit(children[1])
                sup  = visit(children[2])
                sup_txt = f"elevado a {sup}" if sup else ""
                sub_txt = sub if sub else ""
                return strip_ws(f"{base} {sub_txt} {sup_txt}")
        if tag == "mfrac":
            children = list(node)
            if len(children) == 2:
                num = visit(children[0])
                den = visit(children[1])
                return strip_ws(f"{num} sobre {den}")
        if tag == "msqrt":
            children = list(node)
            content = " ".join(visit(c) for c in children)
            return strip_ws(f"raiz quadrada de {content}")
        if tag == "mroot":
            children = list(node)
            if len(children) == 2:
                rad = visit(children[0])
                idx = visit(children[1])
                return strip_ws(f"raiz {idx}-ésima de {rad}")
        if tag == "mrow":
            return strip_ws(" ".join(visit(c) for c in node))
        if tag in ("mtable", "mtr", "mtd"):
            if tag == "mtable":
                rows = []
                for tr in node:
                    if tr.tag.split("}")[-1].lower() != "mtr":
                        continue
                    cells = [strip_ws(visit(td)) for td in tr if td.tag.split("}")[-1].lower()=="mtd"]
                    rows.append("; ".join(cells))
                if rows:
                    rcount = len(rows)
                    ccount = max((len(r.split(";")) for r in rows), default=0)
                    return strip_ws(f"matriz {rcount} por {ccount}: " + " ; ".join(rows))
            return strip_ws(" ".join(visit(c) for c in node))
        return strip_ws(" ".join(visit(c) for c in node)) or strip_ws("".join(node.itertext()))
    
    spoken = visit(root)
    spoken = process_units_and_powers(spoken)
    spoken = normalize_currency(spoken)
    spoken = normalize_numbers(spoken)
    return strip_ws(spoken)

# =======================
# Conversor LaTeX -> Fala (robustecido)
# =======================
def _replace_frac_nested(tex: str) -> str:
    i = 0
    out = []
    while i < len(tex):
        if tex.startswith(r"\frac", i):
            j = i + 5
            while j < len(tex) and tex[j].isspace():
                j += 1
            if j >= len(tex) or tex[j] != "{":
                out.append(tex[i]); i += 1; continue
            num_span = balanced_span(tex, j, "{", "}")
            if not num_span:
                out.append(tex[i]); i += 1; continue
            num = tex[num_span[0]+1:num_span[1]-1]
            k = num_span[1]
            while k < len(tex) and tex[k].isspace():
                k += 1
            if k >= len(tex) or k >= len(tex) or tex[k] != "{":
                out.append(tex[i]); i += 1; continue
            den_span = balanced_span(tex, k, "{", "}")
            if not den_span:
                out.append(tex[i]); i += 1; continue
            den = tex[den_span[0]+1:den_span[1]-1]
            out.append(" " + strip_ws(num) + " sobre " + strip_ws(den) + " ")
            i = den_span[1]
        else:
            out.append(tex[i]); i += 1
    return "".join(out)

def _replace_sqrt_nested(tex: str) -> str:
    i = 0
    out = []
    while i < len(tex):
        if tex.startswith(r"\sqrt", i):
            j = i + 5
            n_txt = None
            while j < len(tex) and tex[j].isspace():
                j += 1
            if j < len(tex) and tex[j] == "[":
                opt = balanced_span(tex, j, "[", "]")
                if opt:
                    n_txt = tex[opt[0]+1:opt[1]-1]
                    j = opt[1]
            while j < len(tex) and tex[j].isspace():
                j += 1
            if j < len(tex) and tex[j] == "{":
                rad = balanced_span(tex, j, "{", "}")
                if rad:
                    content = tex[rad[0]+1:rad[1]-1]
                    if n_txt:
                        out.append(f" raiz {strip_ws(n_txt)}-ésima de {strip_ws(content)} ")
                    else:
                        out.append(f" raiz quadrada de {strip_ws(content)} ")
                    i = rad[1]
                    continue
        out.append(tex[i]); i += 1
    return "".join(out)

def _replace_binom(tex: str) -> str:
    pattern = re.compile(r"\\binom\s*\{([^{}]+)\}\s*\{([^{}]+)\}")
    return pattern.sub(lambda m: f" binomial de {m.group(1).strip()} sobre {m.group(2).strip()} ", tex)

def _replace_limits_ops(tex: str) -> str:
    def repl(m):
        op = m.group(1)
        sub = m.group(2) or ""
        sup = m.group(3) or ""
        op_word = {"int": "integral", "sum": "somatório", "prod": "produtório"}.get(op, op)
        sub = strip_ws(sub)
        sup = strip_ws(sup)
        if op == "sum":
            if sub or sup:
                return f"{op_word} de {sub or ''} até {sup or ''} "
            return f"{op_word} "
        if op in ("int", "prod"):
            if sub or sup:
                return f"{op_word} de {sub or ''} a {sup or ''} "
            return f"{op_word} "
        return f"{op_word} "
    tex = re.sub(r"\\(int|sum|prod)\s*(?:_\s*\{([^{}]*)\})?\s*(?:\^\s*\{([^{}]*)\})?", repl, tex)
    return tex

def _replace_super_sub(tex: str) -> str:
    tex = re.sub(
        r"([A-Za-z0-9]+)\s*\^\s*\{([^{}]+)\}",
        lambda m: _speak_power(m.group(1), m.group(2)),
        tex
    )
    tex = re.sub(
        r"([A-Za-z0-9]+)\s*\^\s*([A-Za-z0-9+\-]+)",
        lambda m: _speak_power(m.group(1), m.group(2)),
        tex
    )
    tex = re.sub(
        r"([A-Za-z0-9]+)\s*_\s*\{([^{}]+)\}",
        lambda m: f"{m.group(1)} {m.group(2)}",
        tex
    )
    tex = re.sub(
        r"([A-Za-z0-9]+)\s*_\s*([A-Za-z0-9]+)",
        lambda m: f"{m.group(1)} {m.group(2)}",
        tex
    )
    return tex

def _speak_power(base: str, exp: str) -> str:
    exp = exp.strip()
    if exp in ("T", "t"):
        return f"{base} transposto"
    if exp == "2":
        return f"{base} ao quadrado"
    if exp == "3":
        return f"{base} ao cubo"
    if exp.startswith("-"):
        return f"{base} à menos {exp[1:]}"
    return f"{base} elevado a {exp}"

@lru_cache(maxsize=50000)
def latex_to_speech_perfect(tex: str) -> str:
    if not tex:
        return ""
    
    tex = safe_unescape(tex)
    tex = clean_latex_backslashes(tex)
    tex = tex.replace("\n", " ").replace("\r", " ")
    tex = tex.replace(r"\\", " ; ")
    
    tex = _replace_frac_nested(tex)
    tex = _replace_sqrt_nested(tex)
    tex = _replace_binom(tex)
    tex = _replace_limits_ops(tex)
    tex = _replace_super_sub(tex)
    
    tex = re.sub(r"\\overline\s*\{([^{}]+)\}", lambda m: f"{m.group(1).strip()} barrado", tex)
    tex = re.sub(r"\\underline\s*\{([^{}]+)\}", lambda m: f"{m.group(1).strip()} sublinhado", tex)
    tex = re.sub(r"\\hat\s*\{([^{}]+)\}", lambda m: f"{m.group(1).strip()} com acento circunflexo", tex)
    tex = re.sub(r"\\bar\s*\{([^{}]+)\}", lambda m: f"{m.group(1).strip()} barrado", tex)
    tex = re.sub(r"\\vec\s*\{([^{}]+)\}", lambda m: f"{m.group(1).strip()} com seta", tex)
    tex = re.sub(r"\\abs\s*\{([^{}]+)\}", lambda m: f" módulo de {m.group(1).strip()} ", tex)
    tex = re.sub(r"\\norm\s*\{([^{}]+)\}", lambda m: f" norma de {m.group(1).strip()} ", tex)
    
    for cmd, replacement in LATEX_CMD_MAP.items():
        if cmd in tex:
            if cmd.startswith("\\") and cmd[1:].isalpha():
                pattern = re.escape(cmd) + r"(?![a-zA-Z])"
                tex = re.sub(pattern, replacement, tex)
            else:
                tex = tex.replace(cmd, replacement)
    
    tex = regex.KEEP_ARG.sub(r" \1 ", tex)
    tex = regex.DROP_COMMANDS.sub(" ", tex)
    tex = re.sub(r"\\begin\{([^}]+)\}", lambda m: " ", tex)
    tex = re.sub(r"\\end\{([^}]+)\}", " ", tex)
    tex = re.sub(r"\\[a-zA-Z]+\*?", " ", tex)
    
    for ch, repl in [("\\", " "), ("{", " "), ("}", " "), ("_", " "), ("^", " "),
                     ("&", " e "), ("%", " por cento "), ("#", " número "), ("$", " "), ("~", " ")]:
        tex = tex.replace(ch, repl)
    
    for char, replacement in UNICODE_MAP.items():
        if char in tex:
            tex = tex.replace(char, replacement)
    
    tex = process_units_and_powers(tex)
    tex = normalize_currency(tex)
    tex = normalize_numbers(tex)
    
    tex = regex.MULTIPLE_SPACES.sub(" ", tex)
    tex = regex.MULTIPLE_DOTS.sub("...", tex)
    tex = re.sub(r"\s+([.,;!?])", r"\1", tex)
    tex = re.sub(r"([.,;!?])([A-Za-z])", r"\1 \2", tex)
    
    return tex.strip()

@lru_cache(maxsize=50000)
def strip_html_perfect(text: str) -> str:
    if not text:
        return ""
    
    text = regex.SOUND_TAG.sub("", text or "")
    text = safe_unescape(text)
    
    text = regex.HTML_SUB.sub(r"\1 \2", text)
    text = regex.HTML_SUP.sub(lambda m: process_units_and_powers(f"{m.group(1)}^{m.group(2)}"), text)
    
    text = regex.HTML_COM.sub("", text)
    text = regex.BLOCK_TAG.sub("", text)
    
    text = regex.BR_TAG.sub(" ", text)
    text = regex.HR_TAG.sub(" ", text)
    text = regex.BR_CLOSERS.sub(" ", text)
    text = regex.BR_OPENERS.sub(" ", text)
    
    for r in (regex.STRONG_TAG, regex.EM_TAG, regex.U_TAG, regex.B_TAG, regex.I_TAG,
              regex.STRIKE_TAG, regex.MARK_TAG, regex.CODE_TAG, regex.LI_TAG, regex.OL_UL_TAG):
        text = r.sub(" ", text)
    
    def _mathml_repl(m):
        return " " + mathml_to_text(m.group(0)) + " "
    text = regex.MATHML.sub(_mathml_repl, text)
    
    text = regex.ANKI.sub(lambda m: " " + latex_to_speech_perfect(m.group(1)) + " ", text)
    text = regex.MJSCRIPT.sub(lambda m: " " + latex_to_speech_perfect(m.group(1)) + " ", text)
    
    text = regex.TAG_ANY.sub(" ", text)
    
    text = regex.DOLLAR2.sub(lambda m: " " + latex_to_speech_perfect(m.group(1)) + " ", text)
    text = regex.DOLLAR1.sub(lambda m: " " + latex_to_speech_perfect(m.group(1)) + " ", text)
    text = regex.PAREN.sub(lambda m: " " + latex_to_speech_perfect(m.group(1)) + " ", text)
    text = regex.BRACK.sub(lambda m: " " + latex_to_speech_perfect(m.group(1)) + " ", text)
    
    entities = {
        "&nbsp;": " ", "&amp;": " e ", "&lt;": " menor que ", "&gt": " maior que ",
        "&quot;": " ", "&apos;": "'", "&mdash;": " - ", "&ndash;": " - ",
        "&hellip;": "...", "&times;": " vezes ", "&divide;": " dividido por ",
        "&plusmn;": " mais ou menos ", "&deg;": " graus ", "&copy;": " copyright ",
        "&reg;": " marca registrada ", "&trade;": " TM ",
    }
    for k, v in entities.items():
        text = text.replace(k, v)
    
    for char, replacement in UNICODE_MAP.items():
        if char in text:
            text = text.replace(char, replacement)
    
    text = process_units_and_powers(text)
    text = normalize_currency(text)
    text = normalize_numbers(text)
    
    for z in ("\u200B", "\u200C", "\u200D", "\u2060", "\ufeff", "\u00A0"):
        text = text.replace(z, " ")
    text = unicodedata.normalize("NFKC", text)
    
    text = regex.MULTIPLE_SPACES.sub(" ", text)
    text = regex.MULTIPLE_DOTS.sub("...", text)
    text = re.sub(r"\s+([.,;!?])", r"\1", text)
    text = re.sub(r"([.,;!?])([A-Za-z])", r"\1 \2", text)
    
    return text.strip()