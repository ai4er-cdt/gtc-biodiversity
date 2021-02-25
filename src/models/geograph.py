"""
Module for processing and analysis of the geospatial graph.

See https://networkx.org/documentation/stable/index.html for graph operations.
"""
import bz2
import gzip
import os
import pathlib
import pickle
from copy import deepcopy
from itertools import zip_longest
from typing import Dict, List, Optional, Tuple, Union

import geopandas as gpd
import networkx as nx
import numpy as np
import rasterio
import rtree as rtree_lib
import shapely
from src.constants import PREFERRED_CRS
from src.data_loading.rasterio_utils import polygonise
from tqdm import tqdm

VALID_EXTENSIONS = (
    ".pickle",
    ".pkl",
    ".gz",
    ".bz2",
    ".shp",
    ".gpkg",
    ".tiff",
    ".tif",
    ".geotif",
    ".geotiff",
)


class GeoGraph:
    """Class for the fragmentation graph."""

    def __init__(
        self,
        data,
        graph_save_path: Optional[Union[str, os.PathLike]] = None,
        raster_save_path: Optional[Union[str, os.PathLike]] = None,
        tolerance: float = 0.0,
        crs: str = PREFERRED_CRS,
        **kwargs,
    ) -> None:
        """
        Class for the fragmentation graph.

        This class can load a pickled networkx graph directly, or create the
        graph from
            - a path to vector data (.shp, .gpkg)
            - a path to raster data  (.tif, .tiff, .geotif, .geotiff)
            - a numpy array containing raster data
            - a dataframe containing polygons.

        Note that when loading vector data, the class label column may not be
        named "class_label", which will cause an error. If loading from a
        dataframe, it must contain a column with this name. Dataframes must also
        contain a "geometry" column containing the polygon data.

        Warning: loading and saving GeoGraphs uses pickle. Loading untrusted
        data using the pickle module is not secure as it can execute arbitrary
        code. Therefore, only load GeoGraphs that come from a trusted source.
        See the pickle documentation for more details:
        https://docs.python.org/3/library/pickle.html

        Args:
            data: Can be a path to a pickle file or compressed pickle file to load
            the graph from, a path to vector data in GPKG or Shapefile format,
            a path to raster data in GeoTiff format, a numpy array containing raster
            data, or a dataframe containing polygons.
            graph_save_path (str or pathlib.Path, optional): A path to a pickle
            file to save the graph to, can be `.gz` or `.bz2`. Defaults to None,
            which will not save the graph.
            raster_save_path (str or pathlib.Path, optional): A path to a file
            to save the polygonised raster data in. A path to a GPKG file is
            recommended, but Shapefiles also work. Defaults to None, which will
            not save the polygonised data.
            tolerance (float, optional): Adds edges between neighbours that are
            at most `tolerance` units apart. Defaults to 0.
            crs (str, optional): Coordinate reference system to set on the
            resulting dataframe. Defaults to None.

            **mask (np.ndarray, optional): Boolean mask that can be applied over
            the polygonisation. Defaults to None.
            **transform (affine.Affine, optional): Affine transformation to
            apply when polygonising. Defaults to the identity transform.
            **connectivity (int, optional): Use 4 or 8 pixel connectivity for
            grouping pixels into features. 8 can cause issues, Defaults to 4.
            **apply_buffer (bool, optional): Apply shapely buffer function to
            the polygons after polygonising. This can fix issues with the
            polygonisation creating invalid geometries.
        """
        super().__init__()
        self._graph = nx.Graph()
        self._habitats: Dict[str, nx.Graph] = {}

        if raster_save_path is not None:
            raster_save_path = pathlib.Path(raster_save_path)
            if raster_save_path.suffix not in (".shp", ".gpkg"):
                raise ValueError("Argument `save_path` should be a GPKG or Shapefile.")
            os.makedirs(raster_save_path.parent, exist_ok=True)
        self.tolerance: float = tolerance
        load_from_graph: bool = False

        # Load from disk
        if isinstance(data, (str, os.PathLike)):
            load_path = pathlib.Path(data)
            assert load_path.exists()
            # Load from saved graph
            if load_path.suffix in (".pickle", ".pkl", ".gz", ".bz2"):
                self._rtree, self._df = self._load_from_graph_path(load_path)
                load_from_graph = True
            # Load from saved vector data
            elif load_path.suffix in (".shp", ".gpkg"):
                self._rtree, self._df = self._load_from_vector_path(load_path)
            # Load from saved raster data
            elif load_path.suffix in (".tiff", ".tif", ".geotif", ".geotiff"):
                self._rtree, self._df = self._load_from_raster_path(
                    load_path, raster_save_path, **kwargs
                )
            else:
                raise ValueError(
                    f"""Extension {load_path.suffix} unknown.
                                 Must be one of {VALID_EXTENSIONS}"""
                )

        # Load from objects in memory
        # Load from dataframe
        elif isinstance(data, gpd.GeoDataFrame):
            self._rtree, self._df = self._load_from_dataframe(
                data, tolerance=self.tolerance
            )
        # Load from raster array
        elif isinstance(data, np.ndarray):
            self._rtree, self._df = self._load_from_raster(
                data, raster_save_path, **kwargs
            )
        else:
            raise ValueError(
                """Type of `data` unknown. Must be a dataframe, numpy
                             array, or file path."""
            )

        # Save resulting graph, if we didn't load from graph.
        if not load_from_graph and graph_save_path is not None:
            graph_save_path = pathlib.Path(graph_save_path)
            if graph_save_path.suffix not in (".pickle", ".pkl", ".gz", ".bz2"):
                raise ValueError(
                    """Argument `graph_save_path` should be a pickle file or
                    compressed file."""
                )
            os.makedirs(graph_save_path.parent, exist_ok=True)
            self._save_graph(graph_save_path)

        if self.df.crs is None:
            self.df.crs = crs
        else:
            self.df = self.df.to_crs(crs)

        print(
            f"Graph successfully loaded with {self.graph.number_of_nodes()} nodes",
            f"and {self.graph.number_of_edges()} edges.",
        )

    @property
    def graph(self) -> nx.Graph:
        """Return networkx graph object."""
        return self._graph

    @graph.setter
    def graph(self, new_graph):
        self._graph = new_graph

    @property
    def rtree(self) -> rtree_lib.index.Index:
        """Return Rtree object."""
        return self._rtree

    @property
    def habitats(self) -> Dict[str, nx.Graph]:
        """Return habitat dictionary."""
        return self._habitats

    @property
    def df(self) -> gpd.GeoDataFrame:
        """Return dataframe containing polygons."""
        return self._df

    @df.setter
    def df(self, new_df):
        self._df = new_df

    @property
    def crs(self):
        """Return crs of dataframe."""
        return self.df.crs

    def _load_from_vector_path(
        self,
        vector_path: pathlib.Path,
        load_slice=None,
    ) -> Tuple[rtree_lib.index.Index, gpd.GeoDataFrame]:
        """
        Load graph and rtree with vector data from GeoPackage or shape file.

        Args:
            vector_path (pathlib.Path): Path to a gpkg or shp file.
            load_slice: A slice object denoting the rows of the dataframe to
            load. Defaults to None, meaning load all rows.

        Returns:
            Tuple: A tuple with the Rtree object used to build the graph and the
            dataframe containing polygon objects.
        """
        # First try to load as GeoPackage, then as Shapefile.
        if slice is not None:
            dataframe = gpd.read_file(
                vector_path, rows=load_slice, enabled_drivers=["GPKG", "ESRI Shapefile"]
            )
        else:
            dataframe = gpd.read_file(
                vector_path, enabled_drivers=["GPKG", "ESRI Shapefile"]
            )
        return self._load_from_dataframe(dataframe, tolerance=self.tolerance)

    def _load_from_raster_path(
        self,
        raster_path: pathlib.Path,
        save_path: Optional[pathlib.Path],
        **raster_kwargs,
    ) -> Tuple[rtree_lib.index.Index, gpd.GeoDataFrame]:
        """
        Load raster data from a GeoTiff file, then load graph and rtree.

        Note: Assumes that relevant data is stored in the first band (band 1)
        by default.

        Args:
            raster_path (pathlib.Path): A path to a file of raster data in
            GeoTiff format.
            save_path (pathlib.Path, optional): A path to a file to save the
            polygonised raster data in. A path to a GPKG file is recommended,
            but Shapefiles also work.

        Returns:
            rtree_lib.index.Index: The Rtree object used to build the graph.
        """
        with rasterio.Env():
            with rasterio.open(raster_path) as image:
                # Load band 1 (Assumes that landcover map is in first band by default)
                data = image.read(1)
        return self._load_from_raster(data, save_path, **raster_kwargs)

    def _load_from_raster(
        self, data_array: np.ndarray, save_path: Optional[pathlib.Path], **raster_kwargs
    ) -> Tuple[rtree_lib.index.Index, gpd.GeoDataFrame]:
        """
        Load raster data, polygonise, then load graph and rtree.

        The raster data should be in GeoTiff format.
        Polygonisation via `rasterio.features.shapes`, which uses `gdal_polygonize`.

        References:
        (1) https://rasterio.readthedocs.io/en/latest/api/rasterio.features.html
        (2) https://gdal.org/programs/gdal_polygonize.html

        Args:
            data_array (np.ndarray): 2D numpy array with the raster data.
            save_path (pathlib.Path, optional): A path to a file to save the
            polygonised raster data in. A path to a GPKG file is recommended,
            but Shapefiles also work.

        Returns:
            Tuple: A tuple with the Rtree object used to build the graph and the
            dataframe containing polygon objects.
        """
        vector_df = polygonise(data_array=data_array, **raster_kwargs)
        if save_path is not None:
            if save_path.suffix == ".gpkg":
                vector_df.to_file(save_path, driver="GPKG")
            else:
                vector_df.to_file(save_path, driver="ESRI Shapefile")
        return self._load_from_dataframe(vector_df, tolerance=self.tolerance)

    def _load_from_graph_path(
        self, graph_path: pathlib.Path
    ) -> Tuple[rtree_lib.index.Index, gpd.GeoDataFrame]:
        """
        Load networkx graph and rtree objects from a pickle file.

        Args:
            graph_path (pathlib.Path): Path to a pickle file. Can be compressed
            with gzip or bz2.

        Returns:
            Tuple: A tuple with the Rtree object used to build the graph and the
            dataframe containing polygon objects.
        """
        if graph_path.suffix == ".bz2":
            with bz2.BZ2File(graph_path, "rb") as bz2_file:
                data = pickle.load(bz2_file)
        elif graph_path.suffix == ".gz":
            with gzip.GzipFile(graph_path, "rb") as gz_file:
                data = pickle.loads(gz_file.read())
        else:
            with open(graph_path, "rb") as file:
                data = pickle.load(file)

        self.graph = data["graph"]
        return data["rtree"], data["dataframe"]

    def _save_graph(self, save_path: pathlib.Path) -> None:
        """
        Save graph with attributes and rtree as pickle file. Can be compressed.

        Args:
            save_path (pathlib.Path): Path to a pickle file. Can be compressed
            with gzip or bz2 by passing filenames ending in `gz` or `bz2`.
        """
        data = {"graph": self.graph, "rtree": self.rtree, "dataframe": self.df}
        if save_path.suffix == ".bz2":
            with bz2.BZ2File(save_path, "wb") as bz2_file:
                pickle.dump(data, bz2_file)
        elif save_path.suffix == ".gz":
            with gzip.GzipFile(save_path, "wb") as gz_file:
                gz_file.write(pickle.dumps(data))
        else:
            with open(save_path, "wb") as file:
                pickle.dump(data, file)

    def _load_from_dataframe(
        self,
        df: gpd.GeoDataFrame,
        tolerance: float = 0.0,
    ) -> Tuple[rtree_lib.index.Index, gpd.GeoDataFrame]:
        """
        Convert geopandas dataframe to networkx graph.

        This code takes around 3 minutes to run on JASMIN for the Chernobyl
        habitat data.

        Args:
            df (gpd.GeoDataFrame): GeoDataFrame containing polygon objects from
            a shape file.
            tolerance (float, optional): Adds edges between neighbours that are
            at most `tolerance` units apart. Defaults to 0.

        Raises:
            ValueError: If `tolerance` < 0, if `class_label` or `geometry` are
            not columns in the dataframe.

        Returns:
            Tuple: A tuple with the Rtree object used to build the graph and the
            dataframe containing polygon objects.
        """
        if tolerance < 0.0:
            raise ValueError("`tolerance` must be greater than 0.")
        if "class_label" not in df.columns:
            raise ValueError("`class_label` must be a column in the dataframe.")
        if "geometry" not in df.columns:
            raise ValueError("`geometry` must be a column in the dataframe.")

        # Reset index to ensure consistent indices
        df = df.reset_index(drop=True)
        # Using this dict and iterating through it is slightly faster than
        # iterating through df due to the dataframe overhead
        geom: Dict[int, shapely.Polygon] = df.geometry.to_dict()
        class_labels: List[int] = df.class_label.tolist()
        # Build Rtree from geometry
        tree = rtree_lib.index.Index()
        for index, polygon in geom.items():
            tree.insert(index, polygon.bounds)
        # this dict maps polygon row numbers in df to a list
        # of neighbouring polygon row numbers
        graph_dict = {}

        # Creating nodes (=vertices) and finding neighbors
        for index, polygon in tqdm(
            geom.items(),
            desc="Step 1 of 2: Creating nodes and finding neighbours",
            total=len(geom),
        ):
            if tolerance > 0:
                # Expand the borders of the polygon by `tolerance```
                new_polygon = polygon.buffer(tolerance)
                # find the indexes of all polygons which intersect with this one
                neighbours: List[int] = [
                    nbr_index
                    for nbr_index in tree.intersection(new_polygon.bounds)
                    if nbr_index != index and geom[nbr_index].intersects(new_polygon)
                ]
            else:
                neighbours = [
                    nbr_index
                    for nbr_index in tree.intersection(polygon.bounds)
                    if nbr_index != index and geom[nbr_index].intersects(polygon)
                ]

            graph_dict[index] = neighbours
            # add each polygon as a node to the graph with useful attributes
            self.graph.add_node(
                index,
                rep_point=polygon.representative_point(),
                area=polygon.area,
                perimeter=polygon.length,
                class_label=class_labels[index],
                bounds=polygon.bounds,
            )

        # iterate through the dict and add edges between neighbouring polygons
        for polygon_id, neighbours in tqdm(
            graph_dict.items(), desc="Step 2 of 2: Adding edges"
        ):
            for neighbour_id in neighbours:
                self.graph.add_edge(polygon_id, neighbour_id)

        return tree, df

    def merge_nodes(
        self, node_list: List[int], class_label: int, final_index: int = None
    ) -> None:
        """
        Merge a list of nodes in the graph together into a single node.

        This will create a node with a neighbour list and polygon which is the
        union of the nodes in `node_list`.

        Args:
            node_list (List[int]): List of integer node indexes in the graph.
            class_label (int): Class label for the resulting node.
            final_index (int, optional): Index to assign to the resulting node.
            Defaults to None, in which case it becomes the highest valid index
            in the dataframe + 1.

        Raises:
            ValueError: If there are invalid nodes in `node_list`, or if
            `final_index` is an existing node not in `node_list`.
        """
        if not all(self.graph.has_node(node) for node in node_list):
            raise ValueError("`node_list` must only contain valid nodes.")
        if (
            final_index is not None
            and final_index not in node_list
            and self.graph.has_node(final_index)
        ):
            raise ValueError(
                "`final_index` cannot be an existing node that is not in `node_list`."
            )
        if final_index is None:
            final_index = self.df.last_valid_index()

        # Build set of all neighbours of nodes in node_list, excluding the
        # nodes in node_list.
        adjacency_set = set()
        for node in node_list:
            adjacency_set.update(list(self.graph.neighbors(node)))
        adjacency_set -= adjacency_set.intersection(node_list)
        # Build union polygon.
        polygon = self.df.geometry.iloc[node_list].unary_union
        # Remove nodes from graph and rows from df
        self.graph.remove_nodes_from(node_list)
        self.df = self.df.drop(node_list)
        # Add final node to graph and df
        self.graph.add_node(
            final_index,
            rep_point=polygon.representative_point(),
            area=polygon.area,
            perimeter=polygon.length,
            class_label=class_label,
            bounds=polygon.bounds,
        )
        data = {"class_label": class_label, "geometry": polygon}
        missing_cols = {key: None for key in set(self.df.columns) - set(data.keys())}
        self.df.loc[final_index] = gpd.GeoSeries(
            {**data, **missing_cols}, crs=self.df.crs
        )
        self.df = self.df.sort_index()
        # Add edges from final node to all neighbours of the original
        self.graph.add_edges_from(
            zip_longest([final_index], adjacency_set, fillvalue=final_index)
        )

    def add_habitat(
        self,
        name: str,
        valid_classes: set,
        max_travel_distance: float = 0.0,
    ) -> None:
        """
        Create habitat graph and store it in habitats dictionary.

        Creates a habitat subgraph of the main GeoGraph that only contains edges
        between nodes in `valid_classes` as long as they are less than
        `max_travel_distance` apart. All nodes which are not in `valid_classes`
        are not in the resulting habitat graph.

        Args:
            name (str): The name of the habitat.
            valid_classes (set): A set of class labels which make up the habitat.
            max_travel_distance (float): The maximum distance the animal(s) in
            the habitat can travel through non-habitat areas. The habitat graph
            will contain edges between any two nodes that have a class label in
            `valid_classes`, as long as they are less than `max_travel_distance`
            units apart. Defaults to 0, which will only create edges between
            directly neighbouring areas.
        """
        hgraph: nx.Graph = deepcopy(self.graph)
        hgraph.graph["name"] = name
        # Remove all edges in the graph, then at the end we only have edges
        # between nodes less than `max_travel_distance` apart
        hgraph.clear_edges()
        # Vectorised buffer on the entire df to calculate the expanded polygons
        # used to get intersections.
        self.df["buff_polygon"] = self.df.geometry.buffer(max_travel_distance)
        # List of nodes that are not in the habitat
        invalid_indexes: List[int] = []
        for node in tqdm(
            hgraph.nodes, desc="Generating habitat graph", total=len(hgraph)
        ):
            if hgraph.nodes[node]["class_label"] not in valid_classes:
                invalid_indexes.append(node)
                continue
            # df.at is a fast df.loc designed only to access single values
            polygon = self.df.at[node, "geometry"]
            buff_poly = self.df.at[node, "buff_polygon"]
            # Query rtree for all polygons within `max_travel_distance` of the original
            poss_neighbours = list(self.rtree.intersection(buff_poly.bounds))
            for nbr in poss_neighbours:
                # If a node is not a habitat class node, don't add the edge
                if hgraph.nodes[nbr]["class_label"] not in valid_classes:
                    continue
                # Otherwise add the edge with distance attribute
                nbr_polygon = self.df.at[nbr, "geometry"]
                if not hgraph.has_edge(node, nbr) and nbr_polygon.intersects(buff_poly):
                    # Since intersects is cheaper than distance, we can save time here
                    if nbr_polygon.intersects(polygon):
                        distance = 0.0
                    else:
                        distance = polygon.distance(nbr_polygon)
                    hgraph.add_edge(node, nbr, distance=distance)

        # Remove expanded polygons from df
        self.df = self.df.drop(columns=["buff_polygon"])
        # Remove non-habitat nodes from habitat graph
        hgraph.remove_nodes_from(invalid_indexes)
        # Add habitat graph to habitats dict
        self._habitats[name] = hgraph

        print(
            f"Habitat successfully loaded with {hgraph.number_of_nodes()} nodes",
            f"and {hgraph.number_of_edges()} edges.",
        )

    def get_graph_components(
        self, graph: nx.Graph
    ) -> Tuple[gpd.GeoDataFrame, List[set]]:
        """Return a GeoDataFrame with graph components.

        This method takes an nx.Graph and determines the individual disconnected
        graph components that make up the graph. Each row of the returned
        GeoDataFrame corresponds to a graph component, with entries in column
        'geometry' being the union of all individual polygons making up a
        component. Warning: this function can only be passed graphs which are a
        subgraph of this class's main `graph` attribute, such as the habitat
        subgraph or the main graph itself.

        This method allows for the UI to visualise components and output their
        number as a metric. Warning: this method is very slow if the graph
        consists mostly of one big component, because taking the union is
        expensive.

        More info on the definition of graph components can be found here:
        https://en.wikipedia.org/wiki/Component_(graph_theory)

        Args:
            graph (nx.Graph): nx.Graph object. This must be a subgraph of this
            class's main `graph` attribute.

        Returns:
            Tuple: A tuple containing the resulting GeoDataFrame and the list of
            graph components.
        """
        components = list(nx.connected_components(graph))
        geom = [self.df.geometry.iloc[list(comp)].unary_union for comp in components]
        gdf = gpd.GeoDataFrame({"geometry": geom}, crs=self.df.crs)
        return gdf, components
