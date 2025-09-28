import os
import random
import matplotlib.pyplot as plt
import networkx as nx
from datetime import datetime

# Default siblings list (used to bootstrap)
DEFAULT_SIBLINGS = ["Aria", "Selene", "Cassandra", "Ivy", "Will"]

# Dimensions we track per relationship
DIMENSIONS = ["affection", "teasing", "conflict"]


# ---------------- Core Management ----------------
def init_relationships(state, siblings=None):
    """Ensure every pair of siblings has a relationship entry in state."""
    siblings = siblings or DEFAULT_SIBLINGS
    rels = state.setdefault("relationships", {})

    for a in siblings:
        for b in siblings:
            if a == b:
                continue
            key = f"{a}→{b}"
            if key not in rels:
                rels[key] = {dim: 0.0 for dim in DIMENSIONS}

    return state["relationships"]


def adjust_relationship(state, a, b, dimension, delta):
    """Safely adjust one dimension between siblings."""
    if a == b or dimension not in DIMENSIONS:
        return

    rels = init_relationships(state)
    key = f"{a}→{b}"
    rels[key][dimension] = max(-1.0, min(1.0, rels[key][dimension] + delta))
    return rels[key][dimension]


def evolve_relationships(state, drift=0.02):
    """Apply small organic random drift to relationships."""
    rels = init_relationships(state)
    for key, vals in rels.items():
        for dim in DIMENSIONS:
            change = random.uniform(-drift, drift)
            vals[dim] = max(-1.0, min(1.0, vals[dim] + change))
    return rels


# ---------------- Visualization ----------------
def plot_relationships(state, save_dir="logs/relationships"):
    """Generate and save a visual map of sibling relationships."""
    rels = state.get("relationships", {})
    if not rels:
        return None

    os.makedirs(save_dir, exist_ok=True)

    G = nx.DiGraph()
    for key, vals in rels.items():
        a, b = key.split("→")
        affection = vals.get("affection", 0.0)
        teasing = vals.get("teasing", 0.0)
        conflict = vals.get("conflict", 0.0)

        if affection > 0.05:
            G.add_edge(a, b, weight=affection, color="green", style="solid")
        if teasing > 0.05:
            G.add_edge(a, b, weight=teasing, color="purple", style="dashed")
        if conflict > 0.05:
            G.add_edge(a, b, weight=conflict, color="red", style="dotted")

    pos = nx.circular_layout(G)
    edges = G.edges()

    # Draw nodes
    nx.draw_networkx_nodes(G, pos, node_size=2000, node_color="lightblue")
    nx.draw_networkx_labels(G, pos, font_size=12, font_weight="bold")

    # Draw edges with attributes
    for edge in edges:
        color = G.edges[edge]["color"]
        style = G.edges[edge]["style"]
        weight = G.edges[edge]["weight"] * 5  # scale thickness
        nx.draw_networkx_edges(
            G, pos, edgelist=[edge], edge_color=color,
            style=style, width=weight, arrows=True
        )

    filename = os.path.join(save_dir, f"relationships_{datetime.now().date()}.png")
    plt.title("Sibling Relationship Map")
    plt.axis("off")
    plt.savefig(filename)
    plt.close()

    return filename
