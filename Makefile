.PHONY: help speckit-help

help: speckit-help

speckit-help:
	@powershell -ExecutionPolicy Bypass -File .specify/scripts/powershell/speckit-help.ps1
