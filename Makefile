sources = $(wildcard datalayers/*.py)
tests = $(wildcard tests/*.py)

.PHONY: test coverage view-coverage clean build publish


build: coverage
	poetry build

publish: build
	poetry publish

# Intentionally have no prerequisites; should be able to run tests even if nothing has changed
test:
	nose2 --verbose

view-coverage: coverage
	firefox htmlcov/index.html

coverage: htmlcov/index.html

.coverage: $(sources) $(tests) .coveragerc
	coverage run -m nose2 --verbose
	coverage report

htmlcov/index.html: .coverage
	coverage html

clean:
	git clean -xdf -e '/venv' -e '/.idea'