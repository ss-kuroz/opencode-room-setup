.PHONY: test sync verify uninstall

PYTHON ?= python3

test:
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) -m py_compile scripts/room.py

sync:
	$(PYTHON) scripts/room.py sync

verify:
	$(PYTHON) scripts/room.py verify --source

uninstall:
	$(PYTHON) scripts/room.py uninstall