import os


def get_files(extension):
    for root, dirnames, filenames in os.walk('.'):
        for filename in filenames:
            if filename.endswith(extension):
                yield os.path.join(root, filename)


def get_roles():
    return sorted(os.listdir('./roles'))


def pytest_generate_tests(metafunc):
    if 'jinja2_file' in metafunc.fixturenames:
        metafunc.parametrize('jinja2_file', get_files('.j2'))

    if 'json_file' in metafunc.fixturenames:
        metafunc.parametrize('json_file', get_files('.json'))

    if 'ini_file' in metafunc.fixturenames:
        metafunc.parametrize('ini_file', get_files('.fact'))

    if 'role' in metafunc.fixturenames:
        metafunc.parametrize('role', get_roles())
