# SpotiBoi
1. Install all requirements

```
pip install -r requirements.txt
```

2. In root directory create ".env" file
Add lines and change values with your Spotify API data:

```
export SPOTIPY_CLIENT_ID='YOUR_API_HERE'
export SPOTIPY_CLIENT_SECRET='YOUR_SECRET_HERE'
export SPOTIPY_REDIRECT_URI='YOUR_REDIRECT_URL_HERE'
export LASTFM_API_KEY = "YOUR_LASTFM_API"
export LASTFM_API_SECRET = "YOUR_LASTFM_SECRET"
```

3. Create new database in bash
```
>> from start_settings import db
>> db.create_all()
```
