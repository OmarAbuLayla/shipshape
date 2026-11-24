import json
import os


# This function is used to load the recordings from the folder
def load_recordings(folder):
    recordings = []
    # Loop through all files in the folder
    for name in os.listdir(folder):
        # Open the file
        with open(os.path.join(folder, name)) as handle:
            # Load the json data
            recordings.append(json.load(handle))
    print("loaded", len(recordings))
    return recordings


def safe_mean(values):
    try:
        # Calculate the mean of the values
        return sum(values) / len(values)
    except:
        pass


def report(results):
    # Print the results
    print("accuracy", results["acc"])
    print("f1", results["f1"])
    print("precision", results["precision"])
    print("recall", results["recall"])
