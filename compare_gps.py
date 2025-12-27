import pandas as pd
import numpy as np
from utils import haversine
import sys
import os

def parse_h11(filepath):
    data = []
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return None
    
    with open(filepath, 'r') as f:
        for line in f:
            if line.startswith('$GNPOS'):
                parts = line.split(',')
                try:
                    # Based on observation:
                    # $GNPOS,lat,lon,...,timestamp_ms(index 18)
                    lat = float(parts[1])
                    lon = float(parts[2])
                    ts_ms = float(parts[18].split('*')[0]) # Handle checksum if present
                    data.append({
                        'timestamp': ts_ms / 1000.0,
                        'h11_lat': lat,
                        'h11_lon': lon
                    })
                except (IndexError, ValueError):
                    continue
    return pd.DataFrame(data)

def parse_embedgps(filepath):
    data = []
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return None

    with open(filepath, 'r') as f:
        for line in f:
            parts = line.strip().split(',')
            try:
                # Format: timestamp, lat, lon, alt
                ts = float(parts[0])
                lat = float(parts[1])
                lon = float(parts[2])
                data.append({
                    'timestamp': ts,
                    'embed_lat': lat,
                    'embed_lon': lon
                })
            except (IndexError, ValueError):
                continue
    return pd.DataFrame(data)

def compare(h11_file, embed_file):
    df_h11 = parse_h11(h11_file)
    df_embed = parse_embedgps(embed_file)
    
    if df_h11 is None or df_embed is None or df_h11.empty or df_embed.empty:
        print("Error: One of the dataframes is empty or could not be loaded.")
        return

    # Sort by timestamp
    df_h11 = df_h11.sort_values('timestamp')
    df_embed = df_embed.sort_values('timestamp')
    
    # Merge using nearest timestamp
    merged = pd.merge_asof(df_embed, df_h11, on='timestamp', direction='nearest', tolerance=1.0)
    
    # Drop rows where we didn't find a match within tolerance
    merged = merged.dropna(subset=['h11_lat', 'h11_lon'])
    
    if merged.empty:
        print("No overlapping data found within the time tolerance.")
        return

    # Calculate distance
    merged['distance_m'] = merged.apply(
        lambda row: haversine(row['embed_lat'], row['embed_lon'], row['h11_lat'], row['h11_lon']), 
        axis=1
    )
    
    print(f"Comparison Summary:")
    print(f"Time range: {merged['timestamp'].min():.2f} to {merged['timestamp'].max():.2f} ({merged['timestamp'].max() - merged['timestamp'].min():.2f} seconds)")
    print(f"Total points compared: {len(merged)}")
    print(f"Mean distance: {merged['distance_m'].mean():.2f} meters")
    print(f"Median distance: {merged['distance_m'].median():.2f} meters")
    print(f"Max distance: {merged['distance_m'].max():.2f} meters")
    print(f"Min distance: {merged['distance_m'].min():.2f} meters")
    print(f"Distance STD: {merged['distance_m'].std():.2f} meters")
    
    # Save results
    output_file = "comparison_results.csv"
    merged.to_csv(output_file, index=False)
    print(f"Detailed results saved to {output_file}")

if __name__ == "__main__":
    h11_path = "data/h11/h11_raw_20251223_0637.txt"
    embed_path = "data/embedgps/embedgps_raw_20251223_0637.txt"
    
    if len(sys.argv) > 2:
        h11_path = sys.argv[1]
        embed_path = sys.argv[2]
    
    compare(h11_path, embed_path)
