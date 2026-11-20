"""L'état d'un VST3 tel que Pedalboard (JUCE) le donne, et comment y mettre un preset de fichier.

`raw_state` d'un VST3 chargé par Pedalboard = b"VC2!" + taille (4 octets) + XML :
    <VST3PluginState><IComponent>taille.base64</IComponent><IEditController>…</IEditController></VST3PluginState>
Le base64 est celui de JUCE (MemoryBlock::toBase64Encoding) : alphabet « .ABC…xyz0123456789+ », 6 bits par
caractère rangés bit de poids faible d'abord. IComponent est l'état que le plugin lui-même enregistre : pour Surge XT,
les mêmes octets qu'un preset .fxp sans son en-tête de 60 octets (« sub3 » + XML du patch + tables d'ondes).

Sert à choisir un preset sans ouvrir la fenêtre (premier essai fait par Claude) ; l'utilisateur, lui, choisit dans
la fenêtre (python -m remaster.choisir).
"""
from __future__ import annotations
import re
import struct

_ALPHABET = ".ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+"
_INDEX = {c: i for i, c in enumerate(_ALPHABET)}


def juce_b64decode(text: str) -> bytes:
    size_s, _, chars = text.partition(".")
    size = int(size_s)
    out = bytearray(size)
    bit = 0
    for c in chars:
        v = _INDEX[c]
        for k in range(6):
            if bit >= size * 8:
                break
            if v >> k & 1:
                out[bit >> 3] |= 1 << (bit & 7)
            bit += 1
    return bytes(out)


def juce_b64encode(data: bytes) -> str:
    nbits = len(data) * 8
    chars = []
    for start in range(0, nbits, 6):
        v = 0
        for k in range(6):
            b = start + k
            if b < nbits and data[b >> 3] >> (b & 7) & 1:
                v |= 1 << k
        chars.append(_ALPHABET[v])
    return f"{len(data)}." + "".join(chars)


def split(raw: bytes) -> tuple[bytes, str]:
    """(état du composant, XML complet) d'un raw_state JUCE VST3."""
    if raw[:4] != b"VC2!":
        raise ValueError("état VST3 inconnu (pas d'en-tête VC2!)")
    n = struct.unpack("<I", raw[4:8])[0]
    xml = raw[8:8 + n].decode("utf-8").rstrip("\0")
    m = re.search(r"<IComponent>([^<]*)</IComponent>", xml)
    if not m:
        raise ValueError("état VST3 sans IComponent")
    return juce_b64decode(m.group(1).strip()), xml


def with_component(raw: bytes, component: bytes) -> bytes:
    """Le même raw_state, avec un autre état du composant."""
    _, xml = split(raw)
    xml = re.sub(r"<IComponent>[^<]*</IComponent>", lambda _: f"<IComponent>{juce_b64encode(component)}</IComponent>",
                 xml, count=1)
    body = xml.encode("utf-8")
    return b"VC2!" + struct.pack("<I", len(body)) + body + b"\0"  # la taille ne compte pas le zéro final


def fxp_chunk(fxp: bytes) -> bytes:
    """Les données d'un preset .fxp « opaque » (FPCh) : ce que le plugin enregistre lui-même."""
    if fxp[:4] != b"CcnK" or fxp[8:12] != b"FPCh":
        raise ValueError("pas un preset .fxp à données opaques (FPCh)")
    size = struct.unpack(">I", fxp[56:60])[0]
    return fxp[60:60 + size]
