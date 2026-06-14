"""Persistence for training/evaluation datasets (``datasets`` table)."""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.dataset import Dataset


class DatasetRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[Dataset]:
        return list(self.db.scalars(select(Dataset).order_by(desc(Dataset.created_at))).all())

    def get(self, dataset_id: str) -> Dataset | None:
        return self.db.get(Dataset, dataset_id)

    def create(
        self,
        *,
        name: str,
        source: str,
        status: str,
        storage_path: str,
        class_names: dict[int, str] | None = None,
    ) -> Dataset:
        dataset = Dataset(
            name=name[:160],
            source=source,
            status=status,
            storage_path=storage_path,
            class_names_json={str(k): v for k, v in (class_names or {}).items()} or None,
        )
        self.db.add(dataset)
        self.db.commit()
        self.db.refresh(dataset)
        return dataset

    def update_counts(
        self,
        dataset_id: str,
        *,
        n_train: int,
        n_val: int,
        n_test: int,
        data_yaml_path: str | None = None,
        status: str | None = None,
    ) -> Dataset:
        dataset = self.get(dataset_id)
        if dataset is None:
            raise KeyError(dataset_id)
        dataset.n_train = n_train
        dataset.n_val = n_val
        dataset.n_test = n_test
        if data_yaml_path is not None:
            dataset.data_yaml_path = data_yaml_path
        if status is not None:
            dataset.status = status
        self.db.commit()
        self.db.refresh(dataset)
        return dataset

    def set_status(self, dataset_id: str, status: str) -> Dataset:
        dataset = self.get(dataset_id)
        if dataset is None:
            raise KeyError(dataset_id)
        dataset.status = status
        self.db.commit()
        self.db.refresh(dataset)
        return dataset

    def set_class_names(self, dataset_id: str, class_names: dict[int, str]) -> Dataset:
        dataset = self.get(dataset_id)
        if dataset is None:
            raise KeyError(dataset_id)
        dataset.class_names_json = {str(k): v for k, v in class_names.items()}
        self.db.commit()
        self.db.refresh(dataset)
        return dataset

    def delete(self, dataset_id: str) -> Dataset:
        dataset = self.get(dataset_id)
        if dataset is None:
            raise KeyError(dataset_id)
        self.db.delete(dataset)
        self.db.commit()
        return dataset
