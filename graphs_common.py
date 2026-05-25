"""Common graph helper utilities."""
import plotly.graph_objects as go


def _add_driver_legend_entries(fig, drivers, row=None, col=None):
    """Add simple color-to-driver legend entries without tying them to metric traces."""
    for driver, color in drivers:
        trace = go.Scatter(
            x=[None],
            y=[None],
            mode='lines',
            name=str(driver),
            line=dict(color=color, width=3),
            hoverinfo='skip',
            showlegend=True,
        )
        if row is not None and col is not None:
            fig.add_trace(trace, row=row, col=col)
        else:
            fig.add_trace(trace)
