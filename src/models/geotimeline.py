"""Module for analysing multiple GeoGraph objects."""
from __future__ import annotations

from typing import Union, List, Dict
import datetime

from src.models.geograph import GeoGraph
from src.models.binary_graph_operations import identify_graphs, NodeMap

# type alias
TimeStamp = Union[int, datetime.datetime]


class NotCachedError(Exception):
    """Basic exception for values which were not yet cached."""


class TimedGeoGraph(GeoGraph):
    """Wrapper class for GeoGraphs with a time attribute"""

    def __init__(self, time: TimeStamp, **geographargs) -> None:
        """
        Simple wrapper class for GeoGraphs with a time attribute.

        Args:
            time (TimeStamp): The timestamp of a given Geograph. Must be an integer or
                a python datetime object.
            **geographargs: Any argument to the GeoGraph class
        """
        super().__init__(**geographargs)
        self._time = time

    @property
    def time(self) -> TimeStamp:
        """Return the time attribute."""
        return self._time


class GeoGraphTimeline:
    """Timeline of multiple GeoGraphs #TODO"""

    def __init__(
        self, data: Union[List[TimedGeoGraph], Dict[TimeStamp, GeoGraph]]
    ) -> None:

        # Initialize empty graphs dict
        self._graphs: Dict[TimeStamp, GeoGraph] = dict()
        # Fill the graphs dict with graphs from `data`
        if isinstance(data, list):
            self._load_from_sequence(graph_list=data)
        elif isinstance(data, dict):
            self._load_from_dict(graph_dict=data)
        else:
            raise NotImplementedError

        # Initialize empty node map cache dictionary
        self._node_map_cache: Dict[(TimeStamp, TimeStamp), NodeMap] = dict()

    @property
    def times(self) -> List[TimeStamp]:
        """Return list of valid time stamps for this GeoGraphTimeline"""
        return list(self._graphs.keys())

    def __getitem__(self, time: TimeStamp) -> GeoGraph:
        """Return the graph at this given time stamp in the GeoGraphTimeline"""
        return self._graphs[time]

    def __len__(self) -> int:
        """Return the number of timestamps in the GeoGraphTimeline"""
        return len(self._graphs)

    def __iter__(self) -> GeoGraph:
        """Iterate over graphs in the GeoGraphTimeline in order (earlier to later)"""
        return iter(self._graphs.values())

    def _sort_by_time(self, reverse: bool = False) -> None:
        """
        Sort the graphs in GeoGraphTimeline accroding to timestamp from earlier to later

        Args:
            reverse (bool, optional): If False, start with the earliest date.
                If True, sort starting with the latest date. Defaults to False.
        """
        self._graphs = {
            time: self._graphs[time] for time in sorted(self._graphs, reverse=reverse)
        }

    def _load_from_sequence(self, graph_list: List[TimedGeoGraph]) -> None:

        # Make sure list is sorted in ascending time order (earliest = left)
        by_time = lambda item: item.time
        self._graphs = {graph.time: graph for graph in sorted(graph_list, key=by_time)}

    def _load_from_dict(self, graph_dict: Dict[TimeStamp, GeoGraph]):

        self._graphs = graph_dict
        self._sort_by_time()

    def identify_graphs(
        self, time1: TimeStamp, time2: TimeStamp, use_cached: bool = True
    ) -> NodeMap:
        """
        Identify the nodes between the graph at time `time1` and `time2` in the timeline

        Args:
            time1 (TimeStamp): timestamp index of the first graph (will be src_graph)
            time2 (TimeStamp): timestamp index of the second graph (will be trg_graph)
            use_cached (bool, optional): Iff True, use cached NodeMaps from previous
                computations. Defaults to True.

        Returns:
            NodeMap: The one-to-many node mapping from `self[time1]` to `self[time2]`
        """

        if use_cached:
            try:
                return self.node_map_cache(time1, time2)
            except NotCachedError:
                pass

        self._node_map_cache[(time1, time2)] = identify_graphs(
            self[time1], self[time2], mode="interior"
        )

        return self._node_map_cache[(time1, time2)]

    def node_map_cache(self, time1: TimeStamp, time2: TimeStamp) -> NodeMap:
        """
        Return cached NodeMap from the graph at `time1` to that at `time2`.

        Args:
            time1 (TimeStamp): Time stamp of the first graph (src_graph)
            time2 (TimeStamp): Time stamp of the second graph (trg_graph)

        Raises:
            NotCachedError: If the combination (time1, time2) or its inverse
                (time2, time1) have not been cached yet.

        Returns:
            NodeMap: The NodeMap to identify nodes from `self[time1]` with `self[time2]`
        """
        if (time1, time2) in self._node_map_cache.keys():
            return self._node_map_cache[(time1, time2)]
        elif (time2, time1) in self._node_map_cache.keys():
            map_from_inverse = self._node_map_cache[(time2, time1)].invert()
            self._node_map_cache[(time1, time2)] = map_from_inverse
            return map_from_inverse
        else:
            raise NotCachedError

    def empty_node_map_cache(self) -> None:
        self._node_map_cache = dict()

    def timestack(self, use_cached: bool = True) -> List[NodeMap]:
        node_maps = []
        for time1, time2 in zip(self.times, self.times[1:]):
            node_maps.append(self.identify_graphs(time1, time2, use_cached))
        return node_maps

    def timediff(self, use_cached: bool = True):
        raise NotImplementedError

    def node_diff_cache(self, time1: TimeStamp, time2: TimeStamp):
        raise NotImplementedError