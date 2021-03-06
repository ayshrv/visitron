# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

""" Evaluation of agent trajectories """

import json
import os
import pprint
import sys
from collections import defaultdict

import networkx as nx
import numpy as np

pp = pprint.PrettyPrinter(indent=4)

from data_loader import VLNDataLoader, VLNDataloader_collate_fn, VLNDataset
from utils_data import load_datasets, load_nav_graphs


class Evaluation(object):
    """ Results submission format:  [{'instr_id': string, 'trajectory':[(viewpoint_id, heading_rads, elevation_rads),] } ] """

    def __init__(self, splits, path_type="planner_path", dataset_type="NDH"):
        self.error_margin = 3.0
        self.splits = splits
        self.gt = {}
        self.instr_ids = []
        self.scans = []

        if dataset_type == "NDH":
            for item in load_datasets(splits, dataset_type="NDH"):
                self.gt[item["inst_idx"]] = item
                self.instr_ids.append(item["inst_idx"])
                self.scans.append(item["scan"])

                # Add 'trusted_path' to gt metadata if necessary.
                if path_type == "trusted_path":
                    planner_goal = item["planner_path"][-1]
                    if planner_goal in item["player_path"][1:]:
                        self.gt[item["inst_idx"]]["trusted_path"] = item["player_path"][
                            :
                        ]
                    else:
                        self.gt[item["inst_idx"]]["trusted_path"] = item[
                            "planner_path"
                        ][:]
        elif dataset_type == "R2R":
            for item in load_datasets(splits, dataset_type="R2R"):
                self.gt[item["inst_idx"]] = item
                self.instr_ids.append(item["inst_idx"])
                self.scans.append(item["scan"])

                self.gt[item["inst_idx"]][""] = item["path"]

                # Add 'trusted_path' to gt metadata if necessary.
                if path_type == "trusted_path":
                    planner_goal = item["planner_path"][-1]
                    if planner_goal in item["player_path"][1:]:
                        self.gt[item["inst_idx"]]["trusted_path"] = item["player_path"][
                            :
                        ]
                    else:
                        self.gt[item["inst_idx"]]["trusted_path"] = item["path"]
        self.scans = set(self.scans)
        self.instr_ids = set(self.instr_ids)
        self.graphs = load_nav_graphs(self.scans)
        self.distances = {}
        self.path_type = path_type
        for scan, G in self.graphs.items():  # compute all shortest paths
            self.distances[scan] = dict(nx.all_pairs_dijkstra_path_length(G))

    def _get_nearest(self, scan, goal_id, path):
        near_id = path[0][0]
        near_d = self.distances[scan][near_id][goal_id]
        for item in path:
            d = self.distances[scan][item[0]][goal_id]
            if d < near_d:
                near_id = item[0]
                near_d = d
        return near_id

    def length(self, scan, nodes):
        return float(
            np.sum(
                [
                    self.distances[scan][edge[0]][edge[1]]
                    for edge in zip(nodes[:-1], nodes[1:])
                ]
            )
        )

    def ndtw(self, scan, prediction, reference):
        dtw_matrix = np.inf * np.ones((len(prediction) + 1, len(reference) + 1))
        dtw_matrix[0][0] = 0
        for i in range(1, len(prediction) + 1):
            for j in range(1, len(reference) + 1):
                best_previous_cost = min(
                    dtw_matrix[i - 1][j], dtw_matrix[i][j - 1], dtw_matrix[i - 1][j - 1]
                )
                cost = self.distances[scan][prediction[i - 1]][reference[j - 1]]
                dtw_matrix[i][j] = cost + best_previous_cost
        dtw = dtw_matrix[len(prediction)][len(reference)]
        ndtw = np.exp(-dtw / (self.error_margin * len(reference)))
        return ndtw

    def cls_metric(self, scan, prediction, reference):
        coverage = np.mean(
            [
                np.exp(
                    -np.min([self.distances[scan][u][v] for v in prediction])
                    / self.error_margin
                )
                for u in reference
            ]
        )
        expected = coverage * self.length(scan, reference)
        score = expected / (expected + np.abs(expected - self.length(scan, prediction)))
        return coverage * score

    def _score_item(self, instr_id, path):
        """Calculate error based on the final position in trajectory, and also
        the closest position (oracle stopping rule)."""
        gt = self.gt[int(instr_id)]
        start = gt[self.path_type][0]
        assert (
            start == path[0][0]
        ), "Result trajectories should include the start position"
        goal = gt[self.path_type][-1]
        planner_goal = gt["planner_path"][
            -1
        ]  # for calculating oracle planner success (e.g., passed over desc goal?)
        final_position = path[-1][0]
        nearest_position = self._get_nearest(gt["scan"], goal, path)
        nearest_planner_position = self._get_nearest(gt["scan"], planner_goal, path)
        dist_to_end_start = None
        dist_to_end_end = None
        for end_pano in gt["end_panos"]:
            d = self.distances[gt["scan"]][start][end_pano]
            if dist_to_end_start is None or d < dist_to_end_start:
                dist_to_end_start = d
            d = self.distances[gt["scan"]][final_position][end_pano]
            if dist_to_end_end is None or d < dist_to_end_end:
                dist_to_end_end = d
        self.scores["nav_errors"].append(
            self.distances[gt["scan"]][final_position][goal]
        )
        self.scores["oracle_errors"].append(
            self.distances[gt["scan"]][nearest_position][goal]
        )
        self.scores["oracle_plan_errors"].append(
            self.distances[gt["scan"]][nearest_planner_position][planner_goal]
        )
        self.scores["dist_to_end_reductions"].append(
            dist_to_end_start - dist_to_end_end
        )
        distance = 0  # Work out the length of the path in meters
        hops = 0
        prev = path[0]
        for curr in path[1:]:
            if prev[0] != curr[0]:
                try:
                    self.graphs[gt["scan"]][prev[0]][curr[0]]
                except KeyError as err:
                    print(
                        "Error: The provided trajectory moves from %s to %s but the navigation graph contains no "
                        "edge between these viewpoints. Please ensure the provided navigation trajectories "
                        "are valid, so that trajectory length can be accurately calculated."
                        % (prev[0], curr[0])
                    )
                    raise
            distance += self.distances[gt["scan"]][prev[0]][curr[0]]
            hops += 1
            prev = curr
        self.scores["trajectory_lengths"].append(distance)
        self.scores["trajectory_hops"].append(hops)
        self.scores["shortest_path_lengths"].append(
            self.distances[gt["scan"]][start][goal]
        )

        gt_vIds = gt[self.path_type]
        path_vIds = [i[0] for i in path]

        self.scores["ndtw"].append(self.ndtw(gt["scan"], path_vIds, gt_vIds))
        self.scores["cls"].append(self.cls_metric(gt["scan"], path_vIds, gt_vIds))

    def score(self, output_file):
        """ Evaluate each agent trajectory based on how close it got to the goal location """
        self.scores = defaultdict(list)
        instr_ids = set(self.instr_ids)
        with open(output_file) as f:
            for item in json.load(f):
                # Check against expected ids
                if item["inst_idx"] in instr_ids:
                    instr_ids.remove(item["inst_idx"])
                    self._score_item(item["inst_idx"], item["trajectory"])
        assert (
            len(instr_ids) == 0
        ), "Trajectories not provided for %d instruction ids: %s" % (
            len(instr_ids),
            instr_ids,
        )
        assert len(self.scores["nav_errors"]) == len(self.instr_ids)

        num_successes = len(
            [i for i in self.scores["nav_errors"] if i < self.error_margin]
        )
        oracle_successes = len(
            [i for i in self.scores["oracle_errors"] if i < self.error_margin]
        )
        oracle_plan_successes = len(
            [i for i in self.scores["oracle_plan_errors"] if i < self.error_margin]
        )

        spls = []
        for err, length, sp in zip(
            self.scores["nav_errors"],
            self.scores["trajectory_lengths"],
            self.scores["shortest_path_lengths"],
        ):
            if err < self.error_margin:
                if sp > 0:
                    spls.append(sp / max(length, sp))
                else:  # In IF, some Q/A pairs happen when we're already in the goal region, so taking no action is correct.
                    spls.append(1 if length == 0 else 0)
            else:
                spls.append(0)

        score_summary = {
            "length": np.average(self.scores["trajectory_lengths"]),
            "hops": np.average(self.scores["trajectory_hops"]),
            "nav_error": np.average(self.scores["nav_errors"]),
            "oracle_success_rate": float(oracle_successes)
            / float(len(self.scores["oracle_errors"])),
            "success_rate": float(num_successes)
            / float(len(self.scores["nav_errors"])),
            "spl": np.average(spls),
            "oracle_path_success_rate": float(oracle_plan_successes)
            / float(len(self.scores["oracle_plan_errors"])),
            "dist_to_end_reduction": sum(self.scores["dist_to_end_reductions"])
            / float(len(self.scores["dist_to_end_reductions"])),
            "ndtw": np.average(self.scores["ndtw"]),
            "cls": np.average(self.scores["cls"]),
        }

        assert score_summary["spl"] <= score_summary["success_rate"]
        return score_summary, self.scores
