#!/usr/bin/env python3
"""
KCBS Event Scraper - Uses browser automation to search for events within radius
"""

import sys
import json
import os
import base64
import urllib.parse
import urllib.request
import ssl
from datetime import datetime, timedelta

# Configuration - read from environment variables
ZIPCODE = os.getenv('ZIPCODE')
if not ZIPCODE:
    print("Error: ZIPCODE environment variable is not set. Please set it in your ~/.bashrc file.")
    sys.exit(1)

# KCBS login credentials (optional - currently not required for public API access)
KCBS_USERNAME = os.getenv('KCBS_USERNAME', '')
KCBS_PASSWORD = os.getenv('KCBS_PASSWORD', '')

RADIUS = "175"
OUTPUT_FILE = "FinalCSV.txt"
KCBS_SEARCH_URL = "https://mms.kcbs.us/members/evr_search_ol_json.php"

def get_date_range():
    """Get date range: today to 1 year from today"""
    today = datetime.now()
    begin_date = today.strftime("%m/%d/%Y")
    end_date = (today + timedelta(days=365)).strftime("%m/%d/%Y")
    return begin_date, end_date

def search_events_by_radius(zipcode, radius):
    """Search KCBS events by radius using the JSON API"""
    begin_date, end_date = get_date_range()
    
    params = {
        'evr_map_type': '0',  # 0 = Search By Radius
        'org_id': 'KCBA',
        'evr_begin': begin_date,
        'evr_end': end_date,
        'evr_address': zipcode,
        'evr_radius': radius,
        'evr_type': '',  # Show All
        'evr_openings': '',
        'evr_region': '',
        'evr_region_type': '',
        'evr_judge': '',
        'evr_keyword': '',
        'evr_rep_name': ''
    }
    
    # Build URL with parameters
    url = f"{KCBS_SEARCH_URL}?" + urllib.parse.urlencode(params)
    
    print(f"Searching for events within {radius} miles of {zipcode}...")
    print(f"Date range: {begin_date} to {end_date}")
    
    try:
        # Create SSL context that doesn't verify certificates (some sites need this)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        # Add authentication if credentials are provided
        # Note: Currently the API endpoint doesn't require authentication, but credentials
        # are available via KCBS_USERNAME and KCBS_PASSWORD environment variables if needed
        if KCBS_USERNAME and KCBS_PASSWORD:
            # Create basic auth header if credentials are provided
            credentials = f"{KCBS_USERNAME}:{KCBS_PASSWORD}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            req.add_header('Authorization', f'Basic {encoded_credentials}')
        
        with urllib.request.urlopen(req, context=ctx) as response:
            data = response.read().decode('utf-8')
            
            # The response might be JSONP, so we need to extract the JSON
            if data.startswith('banner_callback_'):
                # Extract JSON from JSONP callback
                json_start = data.find('{')
                json_end = data.rfind('}') + 1
                if json_start != -1 and json_end > json_start:
                    data = data[json_start:json_end]
            
            try:
                events_data = json.loads(data)
                return events_data
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON: {e}")
                print(f"Response data: {data[:500]}")
                return None
                
    except Exception as e:
        print(f"Error fetching events: {e}")
        return None

def parse_events(events_data):
    """Parse events data and format as pipe-delimited CSV with all required fields"""
    import re
    
    output_lines = []
    
    if not events_data:
        print("No events data received")
        return output_lines
    
    # The structure is GeoJSON FeatureCollection
    events = []
    
    if isinstance(events_data, dict):
        if 'features' in events_data:
            # GeoJSON format
            events = events_data['features']
        elif 'events' in events_data:
            events = events_data['events']
        elif 'data' in events_data:
            events = events_data['data']
        else:
            # Try to find any list in the data
            for key, value in events_data.items():
                if isinstance(value, list):
                    events = value
                    break
    elif isinstance(events_data, list):
        events = events_data
    
    print(f"Found {len(events)} events")
    
    for event in events:
        try:
            # Extract event information from GeoJSON feature
            if isinstance(event, dict) and 'properties' in event:
                props = event['properties']
                name = props.get('name', '')
                html_content = props.get('html_content', '')
                
                # Get event ID from GeoJSON feature (if available)
                event_id = event.get('id') or props.get('id') or props.get('evid') or props.get('event_id')
                
                # Parse event name (from <b> tag or name field)
                name_match = re.search(r'<b>([^<]+)</b>', html_content)
                event_name = name_match.group(1).strip() if name_match else name
                
                # Parse distance (format: "DIST: 106 mi")
                distance_match = re.search(r'DIST:\s*(\d+)\s*mi', html_content)
                distance = distance_match.group(1) + " mi" if distance_match else ''
                
                # Parse date from html_content (format: "1/24/2026 - 1/24/2026" or similar)
                date_match = re.search(r'<i>([^<]+)</i>', html_content)
                dates = date_match.group(1).strip() if date_match else ''
                
                # Parse location from html_content (format: "Henrico, VA 23228")
                # Look for text after </a> and before <br />UNITED STATES
                # Pattern: </a>Henrico, VA 23228<br />UNITED STATES
                location_match = re.search(r'</a>([^<]+)<br[^>]*>UNITED STATES', html_content)
                if not location_match:
                    # Try alternative pattern - look for city, state zip pattern
                    location_match = re.search(r'</a>([A-Za-z\s,]+[A-Z]{2}\s*\d*)<br', html_content)
                location = location_match.group(1).strip() if location_match else ''
                
                # Parse rep name (format: "Reps: BILL JONES" or "Rep : BILL JONES")
                rep_match = re.search(r'Reps?:\s*([^<]+)', html_content)
                rep_name = rep_match.group(1).strip() if rep_match else ''
                
                # Parse event URL from onclick attribute or event ID
                event_url = ''
                if event_id:
                    # Use event ID directly if available
                    event_url = f"https://mms.kcbs.us/members/evr/reg_event_kcba.php?orgcode=KCBA&evid={event_id}"
                else:
                    # Try to extract from onclick attribute (multiple patterns)
                    # Pattern 1: onclick="viewEvent(39161)"
                    event_id_match = re.search(r'onclick=["\']viewEvent\((\d+)\)["\']', html_content)
                    if not event_id_match:
                        # Pattern 2: onclick='viewEvent(39161)'
                        event_id_match = re.search(r"onclick=['\"]viewEvent\((\d+)\)['\"]", html_content)
                    if not event_id_match:
                        # Pattern 3: viewEvent(39161) without quotes
                        event_id_match = re.search(r'viewEvent\((\d+)\)', html_content)
                    
                    if event_id_match:
                        event_id = event_id_match.group(1)
                        event_url = f"https://mms.kcbs.us/members/evr/reg_event_kcba.php?orgcode=KCBA&evid={event_id}"
                    else:
                        # Try to find href attribute
                        href_match = re.search(r'href=["\']([^"\']*evr[^"\']*evid=(\d+)[^"\']*)["\']', html_content)
                        if href_match:
                            event_url = href_match.group(1)
                            if not event_url.startswith('http'):
                                event_url = f"https://mms.kcbs.us{event_url}" if event_url.startswith('/') else f"https://mms.kcbs.us/{event_url}"
                
                # Format: Event Name|Distance|Dates|City, State Zip|Rep Name|Event URL
                if event_name:
                    output_lines.append(f"{event_name}|{distance}|{dates}|{location}|{rep_name}|{event_url}")
                    print(f"  - {event_name} | {distance} | {dates} | {location} | {rep_name} | {event_url}")
        except Exception as e:
            print(f"Error parsing event: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    return output_lines

def main():
    """Main function"""
    print("KCBS Event Scraper - Radius Search")
    print("=" * 50)
    
    # Search for events
    events_data = search_events_by_radius(ZIPCODE, RADIUS)
    
    # Parse events
    output_lines = parse_events(events_data)
    
    # Write to file
    if output_lines:
        with open(OUTPUT_FILE, 'w') as f:
            f.write('\n'.join(output_lines))
        print(f"\n{len(output_lines)} events written to {OUTPUT_FILE}")
    else:
        print(f"\nNo events found. Creating empty {OUTPUT_FILE}")
        with open(OUTPUT_FILE, 'w') as f:
            f.write('')
    
    return 0 if output_lines else 1

if __name__ == "__main__":
    sys.exit(main())

