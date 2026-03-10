import fastf1
import plotly.graph_objects as go
import os

# 1. Setup Caching (Crucial so you don't redownload massive files every time)
cache_dir = 'f1_cache'
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir)
fastf1.Cache.enable_cache(cache_dir)

# 2. Load the Session (2026 Australia Qualifying)
print("Downloading session data... (This might take a minute the first time)")
session = fastf1.get_session(2026, 'Australia', 'Q')
session.load()

# 3. Extract the Fastest Laps for Verstappen (VER) and Norris (NOR)
ver_lap = session.laps.pick_drivers('HAM').pick_fastest()
nor_lap = session.laps.pick_drivers('NOR').pick_fastest()

# 4. Extract Telemetry Data and add a 'Distance' metric
# (We use distance instead of time so the graphs align perfectly on the track)
ver_tel = ver_lap.get_telemetry().add_distance()
nor_tel = nor_lap.get_telemetry().add_distance()

# 5. Build the Interactive Plotly Chart
fig = go.Figure()

# Add Verstappen's Speed Trace
fig.add_trace(go.Scatter(
    x=ver_tel['Distance'],
    y=ver_tel['Speed'],
    mode='lines',
    name=f'Verstappen ({ver_lap["LapTime"].total_seconds():.3f}s)',
    line=dict(color='#0600ef') # Red Bull Blue
))

# Add Norris's Speed Trace
fig.add_trace(go.Scatter(
    x=nor_tel['Distance'],
    y=nor_tel['Speed'],
    mode='lines',
    name=f'Norris ({nor_lap["LapTime"].total_seconds():.3f}s)',
    line=dict(color='#ff8000') # McLaren Papaya
))

# 6. Format the Chart to look like a professional dashboard
fig.update_layout(
    title='Verstappen vs. Norris - 2026 Australian GP Qualifying (Speed Trace)',
    xaxis_title='Distance along track (meters)',
    yaxis_title='Speed (km/h)',
    template='plotly_dark',
    hovermode='x unified', # This lets you hover and see both speeds at the exact same point!
    margin=dict(l=40, r=40, t=60, b=40)
)

# 7. Render it in your browser
fig.show()