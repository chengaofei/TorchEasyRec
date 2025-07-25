# Copyright (c) 2025, Alibaba Group;
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#    http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Any, Dict, List, Optional

import torch
from torch import nn

from tzrec.datasets.utils import Batch
from tzrec.features.feature import BaseFeature
from tzrec.models.rank_model import RankModel
from tzrec.modules.mlp import MLP
from tzrec.protos.model_pb2 import ModelConfig
from tzrec.utils.config_util import config_to_kwargs


class WideAndDeep(RankModel):
    """WideAndDeep model.

    Args:
        model_config (ModelConfig): an instance of ModelConfig.
        features (list): list of features.
        labels (list): list of label names.
        sample_weights (list): sample weight names.
    """

    def __init__(
        self,
        model_config: ModelConfig,
        features: List[BaseFeature],
        labels: List[str],
        sample_weights: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model_config, features, labels, sample_weights, **kwargs)
        self.wide_embedding_dim = self._model_config.wide_embedding_dim
        self.wide_init_fn = self._model_config.wide_init_fn
        self.init_input()

        deep_feature_dim = self.embedding_group.group_total_dim("deep")
        self.deep_mlp = MLP(
            in_features=deep_feature_dim, **config_to_kwargs(self._model_config.deep)
        )
        final_dim = self.deep_mlp.output_dim()
        if self._model_config.HasField("final"):
            self.final_mlp = MLP(
                in_features=1 + final_dim,
                **config_to_kwargs(self._model_config.final),
            )
            final_dim = self.final_mlp.output_dim()

        self.output_mlp = nn.Linear(final_dim, self._num_class)

    def predict(self, batch: Batch) -> Dict[str, torch.Tensor]:
        """Forward the model.

        Args:
            batch (Batch): input batch data.

        Return:
            predictions (dict): a dict of predicted result.
        """
        grouped_features = self.build_input(batch)

        # Wide
        wide_feat = grouped_features["wide"]
        y_wide = torch.sum(wide_feat, dim=1, keepdim=True)

        # Deep
        deep_feat = grouped_features["deep"]
        y_deep = self.deep_mlp(deep_feat)

        if self._model_config.HasField("final"):
            y_cat = torch.cat([y_wide, y_deep], dim=1)
            y_final = self.final_mlp(y_cat)
            y = self.output_mlp(y_final)
        else:
            y = y_wide + self.output_mlp(y_deep)

        return self._output_to_prediction(y)
