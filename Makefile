PREFIX = /usr/local
ENV = PREFIX=$(PREFIX)
.PHONY: clean lint

install: recursive-install
	install -c -m 755 cplay $(PREFIX)/bin/
	install -c -m 644 cplay.1 $(PREFIX)/man/man1

clean: recursive-clean

# pylint: R=refactor, C0103 == Invalid name
lint:
	pycodestyle --ignore=E1,W1,W503,E722 \
		cplay && \
	pylint \
		--indent-string='    ' \
		--disable=missing-docstring,invalid-name,bare-except,useless-object-inheritance,too-many-instance-attributes,too-many-branches,import-outside-toplevel,too-many-public-methods,too-many-locals,too-many-function-args,too-many-lines,consider-using-max-builtin,consider-using-with,global-statement,fixme \
		--extension-pkg-whitelist=alsaaudio \
		cplay
