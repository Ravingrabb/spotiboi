nibba = [
    {'uri' : 123123, 'name': 'Oleg'},
    {'uri' : 141515, 'name': 'Nikich'},
    {'uri' : 152355, 'name': 'Pukich'},
]

names = {
    'suka', 'Oleg'
}

def get_names(nibba):
    for name in nibba:
        yield name['name']

