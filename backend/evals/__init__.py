"""Offline eval harness (PRD §13, §19).

Measures detection quality (precision / recall / F1 / false-positive rate) of the
deterministic Security agent against a small labeled PR dataset, so prompt/model/rule
changes can be scored for regressions in CI.
"""
