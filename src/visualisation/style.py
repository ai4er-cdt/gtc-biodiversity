"""Module providing constants that define style of graph visualisation."""

import branca.colormap

_GRAPH_STYLE = dict(
    style={"color": "black", "fillColor": "snow", "fillOpacity": 0.7},
    hover_style={"fillOpacity": 0.5},
    point_style={"radius": 10},
)

_PGONS_STYLE = dict(
    style={"fillOpacity": 0.8},
    hover_style={"fillOpacity": 0.6},
    border_color="black",
    colormap=branca.colormap.linear.YlOrBr_03,  # See https://colorbrewer2.org/
)

_COMPONENT_STYLE = dict(
    style={"color": "black", "fillColor": "snow", "fillOpacity": 0.7},
    hover_style={"color": "#be3f00", "fillColor": "snow", "fillOpacity": 0.6},
)

_DISCONNECTED_STYLE = dict(
    style={"color": "red", "fillColor": "red", "fillOpacity": 0.6},
    hover_style={"fillOpacity": 0.4},
    point_style={"radius": 20},
)

_POORLY_CONNECTED_STYLE = dict(
    style={"color": "orange", "fillColor": "orange", "fillOpacity": 0.6},
    hover_style={"fillOpacity": 0.4},
    point_style={"radius": 20},
)

_node_dynamics_cmap = branca.colormap.StepColormap(
    colors=[
        "#ff7f00",
        "#fdbf6f",
        "#f3f3f3",
        "#a6cee3",
        "#b2df8a",
        "#33a02c",
        "#6a3d9a",
    ],
    vmin=0,
    vmax=6,
)
_NODE_DYNAMICS_STYLE = dict(
    style={"fillOpacity": 0.75, "weight": 0.1},
    hover_style={"fillOpacity": 0.98, "weight": 1},
    colormap=_node_dynamics_cmap,  # See https://colorbrewer2.org/
    value_min=0,
    value_max=6,
)

DEFAULT_LAYER_STYLE = dict(
    graph=_GRAPH_STYLE,
    pgons=_PGONS_STYLE,
    components=_COMPONENT_STYLE,
    disconnected_nodes=_DISCONNECTED_STYLE,
    poorly_connected_nodes=_POORLY_CONNECTED_STYLE,
)
