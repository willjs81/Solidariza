from __future__ import annotations

import re


def only_digits(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def is_valid_cpf(value: str) -> bool:
    cpf = only_digits(value)
    if len(cpf) != 11:
        return False
    if cpf == cpf[0] * 11:
        return False
    # Validação dígitos verificadores
    for t in [9, 10]:
        s = sum(int(cpf[i]) * (t + 1 - i) for i in range(t))
        d = (s * 10) % 11
        if d == 10:
            d = 0
        if d != int(cpf[t]):
            return False
    return True


def normalize_identifier(value: str) -> str:
    if not value:
        return ""
    digits = only_digits(value)
    if len(digits) == 11:
        # Tratar como CPF se dígitos = 11
        return digits
    # Outros identificadores: remover espaços e upper
    return (value or "").strip().upper()


