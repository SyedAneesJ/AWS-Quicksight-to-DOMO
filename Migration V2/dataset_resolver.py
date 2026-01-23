class StaticDatasetResolver:
    def __init__(self, mapping: dict):
        """
        mapping = { unified_dataset_ref : domo_dataset_id }
        """
        self.mapping = mapping

    def resolve(self, dataset_ref: str) -> str:
        if dataset_ref not in self.mapping:
            raise KeyError(f"No Domo dataset mapping for {dataset_ref}")
        return self.mapping[dataset_ref]
