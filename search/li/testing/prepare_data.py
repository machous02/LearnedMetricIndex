import numpy.typing as npt
import numpy as np
import h5py
import os
from urllib.request import urlretrieve
from pathlib import Path
from typing import Optional
from sklearn.preprocessing import normalize

DATA_DIR = "./data"


def get_sisap23_data_url(type: str, size: str) -> str:
    return f"https://sisap-23-challenge.s3.amazonaws.com/SISAP23-Challenge/laion2B-en-{type}-n={size}.h5"


def get_sisap23_queries_url(type: str) -> str:
    return f"https://sisap-23-challenge.s3.amazonaws.com/SISAP23-Challenge/public-queries-10k-{type}.h5"


def get_sisap23_groundtruth_url(size: str) -> str:
    return f"https://sisap-23-challenge.s3.amazonaws.com/SISAP23-Challenge/laion2B-en-public-gold-standard-v2-{size}.h5"


def get_sisap23_url(
    part: str, type: Optional[str] = None, size: Optional[str] = None
) -> str:
    if part == "data":
        assert type is not None and size is not None
        return get_sisap23_data_url(type, size)

    elif part == "queries":
        assert type is not None
        return get_sisap23_queries_url(type)

    elif part == "groundtruth":
        assert size is not None
        return get_sisap23_groundtruth_url(size)

    assert False


def get_url(
    dataset: str, part: str, type: Optional[str] = None, size: Optional[str] = None
) -> str:
    if dataset == "sisap23":
        return get_sisap23_url(part, type, size)

    assert False


def get_filename(
    part: str, type: Optional[str] = None, size: Optional[str] = None
) -> str:
    if part == "data":
        assert type is not None and size is not None
        return f"data_{type}_{size}.h5"

    elif part == "queries":
        assert type is not None
        return f"queries_{type}.h5"

    elif part == "groundtruth":
        assert size is not None
        return f"groundtruth_{size}.h5"

    assert False


def get_path(
    dataset: str, part: str, type: Optional[str] = None, size: Optional[str] = None
) -> str:
    return os.path.join(DATA_DIR, dataset, get_filename(part, type, size))


def load_data(path: str, emb: str) -> npt.ArrayLike:
    assert os.path.exists(path)

    with h5py.File(path, "r") as f:
        return f[emb][:]


def download(src: str, dst: str) -> None:
    if not os.path.exists(dst):
        os.makedirs(Path(dst).parent, exist_ok=True)
        urlretrieve(src, dst)


def download_data(
    dataset: str, part: str, type: Optional[str] = None, size: Optional[str] = None
) -> None:
    download(get_url(dataset, part, type, size), get_path(dataset, part, type, size))


def get_emb(part: str, type: Optional[str] = None) -> str:
    if part == "groundtruth":
        return "knns"

    if type is not None:
        return {"pca32v2": "pca32", "pca96v2": "pca96", "hammingv2": "hamming"}.get(
            type, "emb"
        )

    return "emb"


def get_data(
    dataset: str, part: str, type: Optional[str] = None, size: Optional[str] = None
) -> npt.ArrayLike:
    path = get_path(dataset, part, type, size)
    if not os.path.exists(path):
        download_data(dataset, part, type, size)

    data = load_data(path, get_emb(part, type))

    if type is not None and type == "hammingv2":
        assert data.dtype == np.uint64
        data = data.view(np.uint8)

    return data


def get_data_normalized(
    dataset: str, part: str, type: Optional[str] = None, size: Optional[str] = None
) -> npt.ArrayLike:
    return normalize(get_data(dataset, part, type, size))


def get_queries(dataset: str, type: str) -> npt.ArrayLike:
    return get_data(dataset, "queries", type=type, size=None)


def get_queries_normalized(dataset: str, type: str) -> npt.ArrayLike:
    return get_data_normalized(dataset, "queries", type=type, size=None)


def get_dataset(dataset: str, type: str, size: str) -> npt.ArrayLike:
    return get_data(dataset, "data", type=type, size=size)


def get_dataset_normalized(dataset: str, type: str, size: str) -> npt.ArrayLike:
    return get_data_normalized(dataset, "data", type=type, size=size)


def get_groundtruth_idxs(dataset: str, size: str) -> npt.ArrayLike:
    return get_data(dataset, "groundtruth", type=None, size=size)
