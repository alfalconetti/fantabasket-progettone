#!/usr/bin/env python3
"""Lancia shared/lottery_verifica.py dal repo (v7.27.3: lo script vero sta in shared/, così il bot lo allega sul
canale). python3 strumenti/lottery_verifica.py simula | matrice | estrai --round R --squadre "…"."""
import os
import runpy

runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared", "lottery_verifica.py"), run_name="__main__")
