.PHONY: run-test run-prod

SHELL := /bin/bash

run-test: aws.test.env venv/bin/activate
	. venv/bin/activate && env $$(cat aws.test.env) gunicorn upload:app --timeout 99999

run-prod: aws.prod.env venv/bin/activate
	. venv/bin/activate && env $$(cat aws.prod.env) gunicorn upload:app --timeout 99999

aws.test.env.gpg: aws.test.env
	gpg --symmetric < aws.test.env > aws.test.env.gpg

aws.prod.env.gpg: aws.prod.env
	gpg --symmetric < aws.prod.env > aws.prod.env.gpg

aws.test.env: aws.test.env.gpg
	gpg --decrypt < aws.test.env.gpg > aws.test.env

aws.prod.env: aws.prod.env.gpg
	gpg --decrypt < aws.prod.env.gpg > aws.prod.env

venv/bin/activate:
	python3 -m venv venv
	. venv/bin/activate && pip install -r requirements.txt

