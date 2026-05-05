"""Shared chart helpers — apply always-visible data labels to Plotly figures."""
import plotly.graph_objects as go


def annotate(
    fig: go.Figure,
    *,
    fmt: str = ",.0f",
    pct: bool = False,
    size: int = 11,
    bar_position: str = "outside",
) -> go.Figure:
    """Add permanent data labels to every trace in *fig* (modifies in place).

    Args:
        fmt:          Python format spec for the numeric value (e.g. ",.0f", ".1f").
        pct:          Append a "%" suffix to every label.
        size:         Font size for labels.
        bar_position: Plotly textposition for Bar traces ("outside", "inside", "auto").
    """
    suffix = "%" if pct else ""
    for trace in fig.data:
        t = trace.type
        if t == "bar":
            orient = getattr(trace, "orientation", None) or "v"
            val = "x" if orient == "h" else "y"
            trace.update(
                texttemplate=f"%{{{val}:{fmt}}}{suffix}",
                textposition=bar_position,
                textfont=dict(size=size),
                cliponaxis=False,
            )
        elif t == "scatter":
            mode = trace.mode or "lines"
            trace.update(
                mode="lines+markers+text",
                texttemplate=f"%{{y:{fmt}}}{suffix}",
                textposition="top center",
                textfont=dict(size=size),
            )
    return fig
