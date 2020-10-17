import pylast
import requests, json

API_KEY = "b6d8eb5b11e5ea1e81a3f116cfa6169f"
API_SECRET = "7108511ff8fee65ba231fba99902a1d5"

username = "Ravingrabb"

network = pylast.LastFMNetwork(api_key=API_KEY, api_secret=API_SECRET,
                               username=username)

def get_recent_tracks(username, number):
    recent_tracks = network.get_user(username).get_recent_tracks(limit=number)
    return recent_tracks

if __name__ == "__main__":
    result = get_recent_tracks(username, 2)
    queries = []
    
    for song in result:
        #album:gold%20artist:abba&type=album 
        query = song[0].title + " artist:" + song[0].artist.name
        #query = "%D0%BA%D0%BE%D0%B3%D0%B4%D0%B0+artist%3A%D0%B8%D1%81%D1%82%D0%BE%D1%87%D0%BD%D0%B8%D0%BA"
        #query = song[0].title
        
        queries.append(query)
        

    print(queries)