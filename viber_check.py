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

recently_played_uris = [
    item
    for item in names
    if item in get_names(nibba)
    ]

recently_played_uris2 = []
for i in names:
    for n in nibba:
        if i in n['name']:
            recently_played_uris2.append(i)

print (recently_played_uris)
print (recently_played_uris2)
