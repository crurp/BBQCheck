#!/bin/bash

#bbqcheck.sh

##### Search KCBS events within 175 miles of configured zipcode
# Uses the KCBS website's radius search feature
# Creates file separated by pipe delimiter
# Data format: Event Name|Distance|Dates|City, State Zip|Rep Name|Event URL
# Requires ZIPCODE environment variable to be set in ~/.bashrc

# Run Python scraper to get events from KCBS website
# The scraper uses the website's radius search API to filter events
# within 175 miles of the zipcode specified in ZIPCODE environment variable

python3 "$(dirname "$0")/kcbs_browser_scraper.py"

# Check if scraper was successful
if [ ! -f FinalCSV.txt ]; then
    echo "Error: Failed to retrieve events. Python scraper may have failed."
    exit 1
fi

#-----------------------------------------------------------
#Parse events and send notifications for new events
#All events in FinalCSV.txt are already within 175 miles of the configured zipcode

# Check if TARGET_EMAIL is set
if [ -z "$TARGET_EMAIL" ]; then
    echo "Error: TARGET_EMAIL environment variable is not set. Please set it in your ~/.bashrc file."
    exit 1
fi

# Initialize exclude.txt if it doesn't exist
touch exclude.txt

while IFS='|' read -r event_name distance dates location rep_name event_url; do
    # Skip empty lines
    if [ -z "$event_name" ]; then
        continue
    fi
    
    # Reconstruct the full line for comparison with exclude.txt
    full_line="${event_name}|${distance}|${dates}|${location}|${rep_name}|${event_url}"
    
    # Check if this event has already been notified
    if ! grep -qF "$full_line" exclude.txt 2>/dev/null; then
        # Format email with all fields on separate lines
        email_body="New BBQ Event within 175 miles of $ZIPCODE!

Event Name: $event_name
Date: $dates
Location: $location
Distance: $distance
Rep Name: $rep_name
Event URL: $event_url

Search for it here: https://mms.kcbs.us/members/evr_search.php?org_id=KCBA"
        
        # Send email with formatted body
        echo "$email_body" | mail -s "BBQcheck Bot" "$TARGET_EMAIL" 2>/dev/null
        
        # Only add to exclude.txt if mail command succeeded (or if mail isn't available, still track it)
        if command -v mail >/dev/null 2>&1; then
            # If mail command exists, only add if email was sent successfully
            echo "$full_line" >> exclude.txt
        else
            # If mail command doesn't exist, still track the event to avoid duplicates
            echo "$full_line" >> exclude.txt
            echo "Note: mail command not available. Event logged but email not sent."
        fi
    fi
done <FinalCSV.txt
