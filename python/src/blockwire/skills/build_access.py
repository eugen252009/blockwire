"""Bounded observed-route history for the grounded builder, not a physics engine.

Only explicit native mesh nodes/edges enter this graph. Mutation projections
SUBTRACT geometry; they never predict a new floor, landing or edge. Distant
segments are historical, not a fresh/atomic world certificate, and every walked
edge must be re-observed. The dependency envelope requires an upright ordinary
player; ``upright_body`` checks existing native tick telemetry, without mutation.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math

from .core import SkillStop

Cell = tuple[int, int, int]
RADIUS = 4
MAX_NODES = 8192
MAX_EDGES = 32768
MAX_FRAME_EDGES = 4096
MAX_ROUTE = 512


def require(ok, reason):
    if not ok:
        raise SkillStop('blocked', reason)


def cell(value) -> Cell:
    require(type(value) in (list, tuple) and len(value) == 3 and all(type(n) is int for n in value), 'access_integer_cell_required')
    x, y, z = value
    require(abs(x) <= 29_999_984 and -2048 <= y <= 2048 and abs(z) <= 29_999_984, 'access_cell_bound')
    return x, y, z


def vector(value, size=3):
    require(type(value) is list and len(value) == size and all(type(n) in (int, float) and math.isfinite(n) for n in value), 'access_finite_vector_required')
    return value


def upright_body(trace, actor, position):
    require(trace.get('profile') == 'native_player_motion_ticks_v1' and trace.get('actor_session') == actor, 'access_body_actor_changed')
    rows = trace.get('samples')
    require(type(rows) is list and len(rows) == 1, 'access_body_sample_required')
    row = rows[0]
    require(row.get('actor_session') == actor and type(row.get('client_tick')) is int and row['client_tick'] >= 0, 'access_body_actor_changed')
    p, b = vector(row.get('position')), vector(row.get('bounding_box'), 6)
    require(row.get('on_ground') is True and row.get('sneaking') is False and math.dist(p, position) <= .2, 'access_body_not_current_upright')
    require(0 < b[3]-b[0] <= .7 and 0 < b[5]-b[2] <= .7 and 1.75 <= b[4]-b[1] <= 1.85
            and abs((b[0]+b[3])/2-p[0]) < .02 and abs((b[2]+b[5])/2-p[2]) < .02 and abs(b[1]-p[1]) < .02,
            'access_unsupported_player_shape')


def floor(p: Cell) -> Cell:
    return p[0], p[1]-1, p[2]


def body(p: Cell):
    return {p, (p[0], p[1]+1, p[2])}


def pair(a, b):
    return tuple(sorted((a, b)))


@dataclass(frozen=True)
class Edge:
    kind: str
    frame: int


def corners(a, b, kind):
    return {(a[0], a[1], b[2]), (b[0], a[1], a[2])} if kind == 'diagonal' else set()


def supports(a, b, kind):
    return {floor(p) for p in {a, b} | corners(a, b, kind)}


def clearance(a, b, kind):
    # Whole voxel supersets of the existing native full-block/step envelopes.
    # They only INVALIDATE observed edges, never manufacture collision clearance.
    low = min(a[1], b[1])
    top = low + (3 if kind == 'step' else 1)
    return {(x, y, z) for x in range(min(a[0], b[0]), max(a[0], b[0])+1)
            for y in range(low, top+1) for z in range(min(a[2], b[2]), max(a[2], b[2])+1)}


@dataclass(frozen=True)
class Retreat:
    actor: str
    frame: int
    kind: str
    changes: tuple[Cell, ...]
    path: tuple[Cell, ...]
    node_frames: tuple[int, ...]
    edge_frames: tuple[int, ...]

    def json(self):
        return {'profile': 'observed_build_retreat_v1', 'actor_session': self.actor, 'frame': self.frame,
                'mutation': self.kind, 'positions': [list(p) for p in self.changes],
                'path': [list(p) for p in self.path], 'node_frames': list(self.node_frames),
                'edge_frames': list(self.edge_frames),
                'all_in_latest_mesh': all(n == self.frame for n in self.node_frames + self.edge_frames),
                'claim': 'observed_route_history_requires_fresh_each_edge', 'traversed': False}


class AccessMap:
    def __init__(self, actor, *, check=lambda: None):
        self.actor, self.check = actor, check
        self.nodes: dict[Cell, int] = {}
        self.edges: dict[tuple[Cell, Cell], Edge] = {}
        self.home = self.current = None
        self.frame = 0

    def update(self, nav):
        self.check()
        require(nav.get('actor_session') == self.actor, 'access_actor_changed')
        require(nav.get('profile') == 'stepped_full_blocks_v1' and nav.get('radius') == RADIUS
                and nav.get('ready') is True and nav.get('on_ground') is True
                and nav.get('current_center_access') is True, 'access_native_mesh_required')
        position = vector(nav.get('position'))
        require(abs(position[1]-round(position[1])) <= .05, 'access_integer_floor_required')
        origin = (math.floor(position[0]), round(position[1]), math.floor(position[2]))
        def inside(p):
            return abs(p[0]-origin[0]) <= RADIUS and abs(p[2]-origin[2]) <= RADIUS and abs(p[1]-origin[1]) <= 2
        rows = nav.get('cells')
        require(type(rows) is list and 1 <= len(rows) <= 405, 'access_mesh_bound')
        positions, safe = [], set()
        for row in rows:
            self.check()
            p = cell(row['position']); hazards = row.get('hazards')
            require(inside(p) and p not in positions, 'access_mesh_position_invalid')
            require(type(hazards) is list and len(hazards) <= 16 and all(type(h) is str for h in hazards), 'access_hazards_required')
            positions.append(p)
            if not hazards: safe.add(p)
        current = cell(nav.get('current_cell'))
        require(current in safe, 'access_current_cell_unknown')
        require(current[1] == origin[1] and abs(position[0]-current[0]-.5) <= .8
                and abs(position[2]-current[2]-.5) <= .8, 'access_current_cell_position_mismatch')
        edges, transitions = nav.get('edges'), nav.get('transitions')
        require(type(edges) is list and type(transitions) is list and max(len(edges), len(transitions)) <= MAX_FRAME_EDGES, 'access_edge_bound')
        def indices(value):
            require(type(value) is list and len(value) == 2 and all(type(n) is int and 0 <= n < len(positions) for n in value)
                    and value[0] != value[1], 'access_edge_indices_invalid')
            return pair(positions[value[0]], positions[value[1]])
        kinds = {}
        for transition in transitions:
            self.check()
            key = indices([transition.get('a'), transition.get('b')]); kind = transition.get('kind')
            require(kind in {'flat', 'diagonal', 'step', 'gap_jump'} and key not in kinds, 'access_transition_invalid')
            kinds[key] = kind
        fresh = {}
        frame = self.frame + 1
        for raw in edges:
            self.check()
            a, b = indices(raw); key = pair(a, b); kind = kinds.get(key)
            require(kind is not None and key not in fresh, 'access_typed_edge_required')
            if kind == 'gap_jump': continue
            dx, dy, dz = [abs(a[i]-b[i]) for i in range(3)]
            require((kind == 'flat' and dy == 0 and dx+dz == 1) or
                    (kind == 'diagonal' and dy == 0 and dx == dz == 1) or
                    (kind == 'step' and dy == 1 and dx+dz == 1), 'access_edge_geometry_invalid')
            if {a, b} | corners(a, b, kind) <= safe:
                fresh[key] = Edge(kind, frame)
        # An omitted/hazardous cell in a refreshed footprint becomes UNKNOWN.
        # Neither old nodes nor old incident/corner-dependent edges survive it.
        nodes = {p: seq for p, seq in self.nodes.items() if not inside(p)}
        nodes.update({p: frame for p in safe})
        retained = {}
        for (a, b), edge in self.edges.items():
            self.check()
            dependencies = {a, b} | corners(a, b, edge.kind)
            if dependencies <= nodes.keys() and not all(inside(p) for p in dependencies):
                retained[a, b] = edge
        retained.update(fresh)
        require(len(nodes) <= MAX_NODES and len(retained) <= MAX_EDGES, 'access_history_budget')
        if self.home is None:
            center = (current[0]+.5, current[1], current[2]+.5)
            require(math.dist(position, center) <= .15, 'access_home_must_be_centered')
            self.home = current
        self.nodes, self.edges, self.current, self.frame = nodes, retained, current, frame
        return self

    def projected(self, kind, changes):
        self.check()
        require(kind in {'place', 'remove'}, 'access_mutation_kind')
        changes = {cell(p) for p in changes}
        require(1 <= len(changes) <= 2, 'access_mutation_bound')
        nodes = {}
        for p, seq in self.nodes.items():
            self.check()
            affected = bool(body(p) & changes) if kind == 'place' else floor(p) in changes
            if not affected: nodes[p] = seq
        edges = {}
        for (a, b), edge in self.edges.items():
            self.check()
            affected = (clearance(a, b, edge.kind) if kind == 'place' else supports(a, b, edge.kind)) & changes
            if a in nodes and b in nodes and not affected:
                edges[a, b] = edge
        return nodes, edges

    def route(self, start, end, *, nodes=None, edges=None, fresh=False):
        self.check()
        nodes, edges = (self.nodes if nodes is None else nodes), (self.edges if edges is None else edges)
        start, end = cell(start), cell(end)
        allowed = {p for p, frame in nodes.items() if not fresh or frame == self.frame}
        if start not in allowed or end not in allowed: return None
        adjacency = {p: [] for p in allowed}
        for (a, b), edge in edges.items():
            self.check()
            if a in allowed and b in allowed and (not fresh or edge.frame == self.frame):
                adjacency[a].append(b); adjacency[b].append(a)
        parents, queue = {start: None}, deque([start])
        while queue:
            self.check()
            p = queue.popleft()
            if p == end:
                path = [p]
                while parents[p] is not None:
                    p = parents[p]; path.append(p)
                require(len(path)-1 <= MAX_ROUTE, 'access_route_budget')
                return tuple(reversed(path))
            for other in sorted(adjacency[p]):
                if other not in parents:
                    parents[other] = p; queue.append(other)
        return None

    def retreat(self, stand, kind, changes):
        self.check()
        stand = cell(stand)
        require(self.home is not None, 'access_home_required')
        require(self.nodes.get(stand) == self.frame, 'access_standing_cell_not_fresh')
        nodes, edges = self.projected(kind, changes)
        path = self.route(stand, self.home, nodes=nodes, edges=edges)
        if path is None: return None
        return Retreat(self.actor, self.frame, kind, tuple(sorted(cell(p) for p in changes)), path,
                       tuple(nodes[p] for p in path), tuple(edges[pair(a,b)].frame for a,b in zip(path,path[1:])))

    def invalidate(self, kind, changes):
        self.nodes, self.edges = self.projected(kind, changes)
