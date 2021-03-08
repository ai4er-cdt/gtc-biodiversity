"""Contains tools for binary operations between GeoGraph objects."""
from __future__ import annotations
from typing import Dict, List
from numpy import ndarray
from src.models.polygon_utils import (
    connect_with_interior_bulk,
    connect_with_interior_or_edge_bulk,
    connect_with_interior_or_edge_or_corner_bulk,
)

# For switching identifiction mode in `identify_node`
_BULK_SPATIAL_IDENTIFICATION_FUNCTION = {
    "corner": connect_with_interior_or_edge_or_corner_bulk,
    "edge": connect_with_interior_or_edge_bulk,
    "interior": connect_with_interior_bulk,
}


class NodeMap:
    """Class to store node mappings between two graphs (the src_graph and trg_graph)"""

    def __init__(
        self,
        src_graph: "GeoGraph",
        trg_graph: "GeoGraph",
        mapping: Dict[int, List[int]],
    ) -> None:
        """
        Class to store node mappings between two graphs (`trg_graph` and `src_graph`)

        This class stores a dictionary of node one-to-many relationships of nodes from
        `src_graph` to `trg_graph`. It also provides support for convenient methods for
        inverting the mapping and bundles the mapping information with references to
        the `src_graph` and `trg_graph`

        Args:
            src_graph (GeoGraph): Domain of the node map (keys in `mapping` correspond
                to indices from the `src_graph`).
            trg_graph (GeoGraph): Image of the node map (values in `mapping` correspond
                to indices from the `trg_graph`)
            mapping (Dict[int, List[int]], optional): A lookup table for the map which
                maps nodes form `src_graph` to `trg_graph`.
        """
        self._src_graph = src_graph
        self._trg_graph = trg_graph
        self._mapping = mapping

    @property
    def src_graph(self) -> "GeoGraph":
        """Keys in the mapping dict correspond to node indices in the `src_graph`"""
        return self._src_graph

    @property
    def trg_graph(self) -> "GeoGraph":
        """Values in the mapping dict correspond to node indices in the `trg_graph`"""
        return self._trg_graph

    @property
    def mapping(self) -> Dict[int, List[int]]:
        """
        Look-up table connecting node indices from `src_graph` to those of `trg_graph`.
        """
        return self._mapping

    def __invert__(self) -> NodeMap:
        """Compute the inverse NodeMap"""
        return self.invert()

    def __eq__(self, other: NodeMap) -> bool:
        """Check two NodeMaps for equality"""
        return (
            self.src_graph == other.src_graph
            and self.trg_graph == other.trg_graph
            and self.mapping == other.mapping
        )

    def invert(self) -> NodeMap:
        """Compute the inverse NodeMap from `trg_graph` to `src_graph`"""
        inverted_mapping = {index: [] for index in self.trg_graph.df.index}

        for src_node in self.src_graph.df.index:
            for trg_node in self.mapping[src_node]:
                inverted_mapping[trg_node].append(src_node)

        return NodeMap(
            src_graph=self.trg_graph, trg_graph=self.src_graph, mapping=inverted_mapping
        )


def identify_node(node: dict, other_graph: "GeoGraph", mode: str = "corner") -> ndarray:
    """
    Return list of all node ids in `other_graph` which identify with the given `node`.

    Args:
        node (dict): The node for which to find nodes in `other_graphs` that can be
            identified with `node`.
        other_graph (GeoGraph): The GeoGraph object in which to search for
            identifications
        mode (str, optional): Must be one of `corner`, `edge` or `interior`. Defaults
            to "corner".
            The different modes correspond to different rules for identification:
            - corner: Polygons of the same `class_label` which overlap, touch in their
                edges or corners will be identified with each other. (fastest)
            - edge: Polygons of the same `class_label` which overlap or touch in their
                edges will be identified with each other.
            - interior: Polygons of the same `class_label` which overlap will be
                identified with each other. Touching corners or edges are not counted.

    Returns:
        np.ndarray: List of node ids in `other_graph` which identify with `node`.
    """
    # Mode switch
    assert mode in ["corner", "edge", "interior"]
    have_valid_overlap = _BULK_SPATIAL_IDENTIFICATION_FUNCTION[mode]

    # Get potential candidates for overlap
    candidate_ids = other_graph.rtree.query(node["geometry"], sort=True)
    # Filter candidates according to the same class label
    candidate_ids = candidate_ids[
        other_graph.class_label[candidate_ids] == node["class_label"]
    ]
    # Filter candidates accroding to correct spatial overlap
    candidate_ids = candidate_ids[
        have_valid_overlap(node["geometry"], other_graph.geometry[candidate_ids])
    ]

    return candidate_ids


def identify_graphs(graph1: "GeoGraph", graph2: "GeoGraph", mode: str) -> NodeMap:
    """
    Idenitfy all nodes from `graph1` with nodes from `graph2` based on the given `mode`

    Args:
        graph1 (GeoGraph): The GeoGraph whose node indicies will form the domain
        graph2 (GeoGraph): The GeoGraph whose node indices will form the image (target)
        mode (str): The mode to use for node identification. Must be one of `corner`,
            `edge` or `interior`.
            The different modes correspond to different rules for identification:
            - corner: Polygons of the same `class_label` which overlap, touch in their
                edges or corners will be identified with each other. (fastest)
            - edge: Polygons of the same `class_label` which overlap or touch in their
                edges will be identified with each other.
            - interior: Polygons of the same `class_label` which overlap will be
                identified with each other. Touching corners or edges are not counted.

    Returns:
        NodeMap: A NodeMap containing the map from `graph1` to `graph2`.
    """

    mapping = {index1: [] for index1 in graph1.df.index}

    for index in graph1.df.index:  # TODO: Speed up & enable trivial parallelisation
        mapping[index] = graph1.identify_node(index, graph2, mode=mode)

    return NodeMap(src_graph=graph1, trg_graph=graph2, mapping=mapping)


def graph_polygon_diff(node_map: NodeMap):
    raise NotImplementedError
