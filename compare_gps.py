import pandas as pd
import numpy as np
from utils import haversine
import sys
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

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
                    # $GNPOS,lat,lon,alt,...,timestamp_ms(index 18)
                    lat = float(parts[1])
                    lon = float(parts[2])
                    alt = float(parts[3])
                    ts_ms = float(parts[18].split('*')[0]) # Handle checksum if present
                    data.append({
                        'timestamp': ts_ms / 1000.0,
                        'h11_lat': lat,
                        'h11_lon': lon,
                        'h11_alt': alt
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
                alt = float(parts[3])
                data.append({
                    'timestamp': ts,
                    'embed_lat': lat,
                    'embed_lon': lon,
                    'embed_alt': alt
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
    
    # Calculate altitude difference
    merged['alt_diff_m'] = merged['embed_alt'] - merged['h11_alt']
    
    print(f"Comparison Summary:")
    print(f"Time range: {merged['timestamp'].min():.2f} to {merged['timestamp'].max():.2f} ({merged['timestamp'].max() - merged['timestamp'].min():.2f} seconds)")
    print(f"Total points compared: {len(merged)}")
    print(f"Mean horizontal distance: {merged['distance_m'].mean():.2f} meters")
    print(f"Median horizontal distance: {merged['distance_m'].median():.2f} meters")
    print(f"Max horizontal distance: {merged['distance_m'].max():.2f} meters")
    print(f"Horizontal Distance STD: {merged['distance_m'].std():.2f} meters")
    print("-" * 30)
    print(f"Mean altitude diff: {merged['alt_diff_m'].mean():.2f} meters")
    print(f"Median altitude diff: {merged['alt_diff_m'].median():.2f} meters")
    print(f"Max altitude diff: {merged['alt_diff_m'].max():.2f} meters")
    print(f"Altitude diff STD: {merged['alt_diff_m'].std():.2f} meters")
    
    # Save results
    output_file = "comparison_results.csv"
    merged.to_csv(output_file, index=False)
    print(f"Detailed results saved to {output_file}")

    # Plotting
    try:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 12))
        
        # Trajectory plot
        ax1.plot(merged['h11_lon'], merged['h11_lat'], label='H11 GPS', alpha=0.7)
        ax1.plot(merged['embed_lon'], merged['embed_lat'], label='Embed GPS', alpha=0.7)
        ax1.set_xlabel('Longitude')
        ax1.set_ylabel('Latitude')
        ax1.set_title('GPS Trajectory Comparison')
        ax1.legend()
        ax1.grid(True)
        
        # Altitude comparison plot
        relative_time = merged['timestamp'] - merged['timestamp'].min()
        ax2.plot(relative_time, merged['h11_alt'], label='H11 Altitude', alpha=0.7)
        ax2.plot(relative_time, merged['embed_alt'], label='Embed Altitude', alpha=0.7)
        ax2.set_xlabel('Time (s)')
        ax2.set_ylabel('Altitude (m)')
        ax2.set_title('Altitude Comparison over Time')
        ax2.legend()
        ax2.grid(True)
        
        plt.tight_layout()
        plot_file = "comparison_plot.png"
        plt.savefig(plot_file)
        print(f"Plot saved to {plot_file}")
    except Exception as e:
        print(f"Error during plotting: {e}")

if __name__ == "__main__":
    matplotlib.rc("font", family="DejaVu Sans") 
    h11_path, embed_path = [
        ("data/h11/h11_raw_20251223_0745_youke_out_10hz.txt",
     "data/embedgps/embedgps_raw_20251223_0745.txt"), #idx=0
        ("data/h11/h11_raw_20251223_0752_youke_in_10hz.txt",
     "data/embedgps/embedgps_raw_20251223_0752.txt"), #idx=1
     ][0]
    
    if len(sys.argv) > 2:
        h11_path = sys.argv[1]
        embed_path = sys.argv[2]
    
    compare(h11_path, embed_path)
