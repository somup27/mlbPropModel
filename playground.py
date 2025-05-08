import os
import pickle

pickle_path = os.path.join(os.getcwd(), "bets.pkl")

if os.path.exists(pickle_path) and os.path.getsize(pickle_path) > 0:
    with open(pickle_path, "rb") as f:
        bets = pickle.load(f)
        print(bets)
else:
    print("Pickle file missing or empty. Initializing...")
    bets = {"ungraded_bets": [], "graded_bets": []}
    with open(pickle_path, "wb") as f:
        pickle.dump(bets, f)
