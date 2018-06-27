import json

import pytest

from jinja2 import Template


def test_jinja2_file(jinja2_file):
    with open(jinja2_file, 'rb') as f:
        template_text = f.read().decode('utf-8')

    try:
        Template(template_text)

    except Exception as e:
        pytest.fail('%s is not valid Jinja2:\n%s' % (jinja2_file, e))


def test_json_file(json_file):
    try:
        with open(json_file, mode='rb') as f:
            json.load(f, encoding='utf-8')

    except Exception as e:
        pytest.fail('%s is not valid JSON:\n%s' % (json_file, e))
