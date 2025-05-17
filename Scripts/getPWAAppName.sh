#!/bin/bash

# If no argument is passed, get the focused window's class using xprop
if [ -z "$1" ]; then
    # Get the focused window's class using xprop
    className=$(xprop -root | grep "_NET_ACTIVE_WINDOW(WINDOW)" | awk '{print $5}' | xargs -I {} xprop -id {} WM_CLASS | awk -F'\"' '{print $4}')
    # echo "No argument, using focused window class: $className"
else
    # Use the class ID passed as an argument
    className="$1"
fi

# Run the `firefoxpwa profile list` command and capture the output
profileList=$(firefoxpwa profile list)

# Function to extract app name from profile list
extractAppName() {
    local appID="$1"
    # Search for the app ID in the profile list and extract the app name
    echo "$profileList" | grep -A 2 "$appID" | sed 's/^\- \([^:]*\):.*$/\1/'
}

# Function to check if the window class matches an app ID in the profile list
findAppByWindowClass() {
    local windowClass="$1"
    
    # Check if any of the app IDs match the window class (assumed to be part of the output)
    appID=$(echo "$windowClass" | grep FFPWA- | sed 's/^FFPWA-//')
    
    # If an ID was found, extract the app name
    if [[ -n "$appID" ]]; then
        # echo "Using appID: $appID"
        extractAppName "$appID"
    else
        # echo "No appID found. Returning the original windowClass."
        echo "$windowClass"
    fi
}

# Find the app based on the class name
if [[ -n "$className" ]]; then
    # echo "Finding app with className: $className"
    findAppByWindowClass "$className"
else
    echo "No window class found. Please ensure the focused window is related to a known app."
fi

