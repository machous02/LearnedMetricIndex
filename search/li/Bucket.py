import numpy as np
import numpy.typing as npt
import pandas as pd
import time

from li.inverted_file import InvertedFileIndex
from typing import Tuple, Any, Optional
import faiss


class Bucket:
    data: Any
    original_idxs: npt.ArrayLike
    subset_parameter: int

    def train(self, data: npt.NDArray[np.float32], **kwargs) -> float:
        raise NotImplementedError()

    def add(
        self, data: npt.NDArray[np.float32], original_idxs: npt.ArrayLike, **kwargs
    ) -> float:
        raise NotImplementedError()

    def build(
        self, data: npt.NDArray[np.float32], original_idxs: npt.ArrayLike, **kwargs
    ) -> float:
        return self.train(data, **kwargs) + self.add(data, original_idxs, **kwargs)

    def reset(self) -> None:
        raise NotImplementedError()

    def search(
        self, queries: npt.NDArray[np.float32], k: int, **kwargs
    ) -> Tuple[npt.NDArray[np.int32], npt.NDArray[np.float32], float, int]:
        raise NotImplementedError()

    def _search_impl(
        self, queries: npt.NDArray[np.float32], k: int, **kwargs
    ) -> Tuple[npt.NDArray[np.int32], npt.NDArray[np.float32], float, int]:
        raise NotImplementedError()

    def search_with_subcluster_no(
        self,
        queries: npt.NDArray[np.float32],
        k: int,
        subclusters_to_search: npt.NDArray[np.int32],
        **kwargs
    ) -> Tuple[
        npt.NDArray[np.int32],
        npt.NDArray[np.float32],
        float,
        int,
        npt.NDArray[np.uint32],
    ]:
        assert len(queries) == len(subclusters_to_search)

        indices = np.empty((len(queries), k), dtype=np.int32)
        distances = np.empty((len(queries), k))
        t_search = 0.0
        distance_computations = 0
        subclusters_searched = np.empty(len(queries), dtype=np.int32)
        sketches = kwargs.get("sketches", None)

        for subcluster_no in np.unique(subclusters_to_search):
            query_indices = subclusters_to_search == subcluster_no
            self.subset_parameter = int(subcluster_no)

            if sketches is not None:
                kwargs["sketches"] = sketches[query_indices]

            ind, dis, t, dc = self._search_impl(queries[query_indices], k, **kwargs)

            indices[query_indices] = ind
            distances[query_indices] = dis
            t_search += t
            distance_computations += dc
            subclusters_searched[query_indices] = self.subset_parameter

        kwargs["sketches"] = sketches

        return indices, distances, t_search, distance_computations, subclusters_searched


class NaiveBucket(Bucket):
    data: Optional[npt.NDArray[np.float32]]

    def train(self, data: npt.NDArray[np.float32], **kwargs) -> float:
        return 0.0

    def add(
        self, data: npt.NDArray[np.float32], original_idxs: npt.ArrayLike, **kwargs
    ) -> float:
        assert len(data) == len(original_idxs)

        self.original_idxs = original_idxs
        t_start = time.time()
        self.data = data
        return time.time() - t_start

    def reset(self) -> None:
        self.data = None

    def search(
        self, queries: npt.NDArray[np.float32], k: int, **kwargs
    ) -> Tuple[npt.NDArray[np.int32], npt.NDArray[np.float32], float, int]:
        return self._search_impl(queries, k, **kwargs)

    def _search_impl(
        self, queries: npt.NDArray[np.float32], k: int, **kwargs
    ) -> Tuple[npt.NDArray[np.int32], npt.NDArray[np.float32], float, int]:
        assert self.data is not None

        s = time.time()
        similarity, indices = faiss.knn(
            queries,
            self.data,
            k,
            metric=faiss.METRIC_INNER_PRODUCT,
        )
        t_search = time.time() - s

        distances = 1 - similarity  # similarity is not distance

        return indices, distances, t_search, len(queries) * len(self.data)


class IVFBucket(Bucket):
    data: Optional[InvertedFileIndex] = None

    def train(self, data: npt.NDArray[np.float32], **kwargs) -> float:
        nlist = kwargs.get("nlist", 5)
        nlist = min(nlist, len(data))

        no, d = data.shape
        s = time.time()
        self.data = InvertedFileIndex(d, nlist)
        self.data.train(data)

        return time.time() - s

    def add(
        self, data: npt.NDArray[np.float32], original_idxs: npt.ArrayLike, **kwargs
    ) -> float:
        assert self.data is not None and self.data.trained
        assert len(data) == len(original_idxs)

        self.original_idxs = original_idxs
        s = time.time()
        self.data.add(data)

        return time.time() - s

    def reset(self) -> None:
        self.data.reset()

    def search(
        self, queries: npt.NDArray[np.float32], k: int, **kwargs
    ) -> Tuple[npt.NDArray[np.int32], npt.NDArray[np.float32], float, int]:
        self.subset_parameter = kwargs.get("nprobe", 5)
        return self._search_impl(queries, k, **kwargs)

    def _search_impl(
        self, queries: npt.NDArray[np.float32], k: int, **kwargs
    ) -> Tuple[npt.NDArray[np.int32], npt.NDArray[np.float32], float, int]:
        assert self.data is not None and self.data.trained

        nprobe = self.subset_parameter
        nprobe = min(nprobe, self.data.nlist)
        self.subset_parameter = nprobe

        self.data.nprobe = nprobe

        s = time.time()
        dc = self.data.distance_computer.distance_computations
        vectors, distances = self.data.search(
            queries,
            k,
        )
        t_search = time.time() - s

        return (
            vectors,
            distances,
            t_search,
            self.data.distance_computer.distance_computations - dc,
        )


class IVFBucketFaiss(Bucket):
    data: Optional[faiss.IndexIVFFlat] = None

    def train(self, data: npt.NDArray[np.float32], **kwargs) -> float:
        nlist = kwargs.get("nlist", 5)
        nlist = min(nlist, len(data))

        no, d = data.shape
        s = time.time()
        quantizer = faiss.IndexFlatIP(d)
        self.data = faiss.IndexIVFFlat(quantizer, d, nlist)
        self.data.train(data)

        return time.time() - s

    def add(
        self, data: npt.NDArray[np.float32], original_idxs: npt.ArrayLike, **kwargs
    ) -> float:
        self.original_idxs = original_idxs

        s = time.time()
        self.data.add(data)

        return time.time() - s

    def reset(self) -> None:
        self.data.reset()

    def search(
        self, queries: npt.NDArray[np.float32], k: int, **kwargs
    ) -> Tuple[npt.NDArray[np.int32], npt.NDArray[np.float32], float, int]:
        self.subset_parameter = kwargs.get("nprobe", 5)
        return self._search_impl(queries, k, **kwargs)

    def _search_impl(
        self, queries: npt.NDArray[np.float32], k: int, **kwargs
    ) -> Tuple[npt.NDArray[np.float32], npt.NDArray[np.int32], float, int]:
        assert self.data is not None
        nprobe = self.subset_parameter
        nprobe = min(nprobe, self.data.nlist)
        self.subset_parameter = nprobe

        self.data.nprobe = nprobe

        s = time.time()
        distances, indices = self.data.search(
            queries,
            k,
        )
        t_search = time.time() - s

        return indices, distances, t_search, np.NINF


class SketchBucket(Bucket):
    data: Optional[npt.NDArray[np.float32]] = None
    sketch_index: Optional[faiss.IndexBinaryFlat] = None

    def train(self, data: npt.NDArray[np.float32], **kwargs) -> float:
        sketches = kwargs.get("sketches", None)
        assert sketches is not None
        assert len(data) == len(sketches)

        no, d = sketches.shape
        self.sketch_index = faiss.IndexBinaryFlat(d * 8)
        return 0.0

    def add(
        self, data: npt.NDArray[np.float32], original_idxs: npt.ArrayLike, **kwargs
    ) -> float:
        sketches = kwargs.get("sketches", None)
        assert sketches is not None
        assert len(data) == len(original_idxs)
        assert len(data) == len(sketches)
        assert self.sketch_index is not None

        self.original_idxs = original_idxs
        t_start = time.time()
        self.data = data
        self.sketch_index.add(sketches)
        return time.time() - t_start

    def reset(self) -> None:
        self.data = None
        self.sketch_index.reset()

    def search(
        self, queries: npt.NDArray[np.float32], k: int, **kwargs
    ) -> Tuple[npt.NDArray[np.int32], npt.NDArray[np.float32], float, int]:
        self.subset_parameter = kwargs.get("c", k * 10)
        return self._search_impl(queries, k, **kwargs)

    def _search_impl(
        self, queries: npt.NDArray[np.float32], k: int, **kwargs
    ) -> Tuple[npt.NDArray[np.int32], npt.NDArray[np.float32], float, int]:
        sketches = kwargs.get("sketches", None)
        assert self.data is not None
        assert self.sketch_index is not None
        assert sketches is not None
        assert len(queries) == len(sketches)

        c = self.subset_parameter
        c = min(c, len(self.data))
        self.subset_parameter = c

        s_t = time.time()
        sketch_distances, sketch_indices = self.sketch_index.search(
            sketches,
            c,
        )

        dc = 0
        sim = []
        ind = []

        for query_idx, query in enumerate(queries):
            s, i = faiss.knn(
                [query],
                self.data[sketch_indices[query_idx]],
                k,
                metric=faiss.METRIC_INNER_PRODUCT,
            )

            sim.append(s[0])
            ind.append(sketch_indices[query_idx, i[0]])
            dc += len(sketch_indices[query_idx])

        t_search = time.time() - s_t

        similarity = np.array(sim)
        indices = np.array(ind)

        distances = 1 - similarity

        return indices, distances, t_search, dc
