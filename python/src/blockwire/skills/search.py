"""Targeted read-only perception: NEW native rays, never walking or camera planning."""
import asyncio
import math
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .core import SkillParameters, SkillDefinition, SkillResult, SkillStop
from ..errors import NativeOperationError

PROFILE = 'targeted_surface_search_v1'
SIDE, PAGE_SIZE, PAGES, MAX_MATCHES = 65, 128, 34, 32
TARGET_PATTERN = r'^(logs|[a-z0-9_.-]+:[a-z0-9_./-]+)$'
LOGS = frozenset('minecraft:'+wood+'_log' for wood in
    ('oak', 'spruce', 'birch', 'jungle', 'acacia', 'dark_oak', 'mangrove', 'cherry', 'pale_oak'))
Target = Annotated[str, Field(min_length=1, max_length=128, pattern=TARGET_PATTERN)]
Vector = Annotated[list[float], Field(min_length=3, max_length=3)]


class Search(SkillParameters):
    target: Target = Field(default='logs', description='Exact namespaced block ID, or logs: nine vanilla unstripped log IDs, not planks/leaves or proof of natural origin.')
    range: int = Field(default=64, ge=1, le=64, description='Maximum eye-to-surface ray length in blocks, not interaction reach.')
    cone_degrees: int = Field(default=30, ge=10, le=90, description='Full 3D cone around the current player-eye direction. No camera turn or centre-hit requirement.')
    timeout_seconds: float = Field(default=10., ge=.1, le=30.)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class SearchPage(StrictModel):
    target: Target = 'logs'
    range: int = Field(default=64, ge=1, le=64)
    cone_degrees: int = Field(default=30, ge=10, le=90)
    page: int = Field(default=0, ge=0, lt=PAGES)
    view_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def view_required(self):
        if self.page and self.view_id is None:raise ValueError('Subsequent pages require the original view_id')
        return self


class Hit(StrictModel):
    id: str = Field(min_length=1, max_length=128, pattern=r'^[a-z0-9_.-]+:[a-z0-9_./-]+$')
    position: list[int] = Field(min_length=3, max_length=3)
    aim_position: Vector
    distance_blocks: float = Field(ge=0, le=64.001)
    eye_distance_to_center: float = Field(ge=0, le=68)
    face: Literal['up', 'down', 'north', 'south', 'east', 'west']


class PageResult(StrictModel):
    profile: Literal['targeted_surface_search_v1']
    actor_session: str = Field(min_length=1, max_length=128)
    target: Target
    range: int = Field(ge=1, le=64)
    cone_degrees: int = Field(ge=10, le=90)
    page: int = Field(ge=0, lt=PAGES)
    pages: Literal[34]
    next_page: int | None
    view_id: str = Field(pattern=r'^[0-9a-f]{64}$')
    visited_cells: int = Field(ge=1, le=PAGE_SIZE)
    rays_cast: int = Field(ge=0, le=PAGE_SIZE)
    truncated: bool
    sampled_at_ms: int = Field(ge=0)
    eye_position: Vector
    forward: Vector
    matches: list[Hit] = Field(max_length=MAX_MATCHES)


class SearchScan:
    """Bounded page accumulator; changing actor/view discards the entire result."""
    def __init__(self, goal, actor):
        if not isinstance(actor, str) or not 1 <= len(actor) <= 128:raise SkillStop('blocked', 'actor_session_required')
        self.goal, self.actor = goal, actor
        self.page = 0; self.view = None; self.pose = None; self.rows = {}; self.cells = self.rays = 0
        self.done = self.complete = self.limited = False; self.first_ms = self.last_ms = None

    def request(self):
        if self.done:raise ValueError('Search already terminal; never replay pages')
        return SearchPage(target=self.goal.target, range=self.goal.range, cone_degrees=self.goal.cone_degrees,
                          page=self.page, view_id=self.view).model_dump(exclude_none=True)

    def accept(self, raw):
        try:r = PageResult.model_validate(raw)
        except ValueError as error:raise SkillStop('blocked', 'invalid_search_response') from error
        if r.actor_session != self.actor:raise SkillStop('blocked', 'actor_session_changed')
        pose = (r.eye_position, r.forward)
        if self.view is not None and (r.view_id != self.view or pose != self.pose):raise SkillStop('blocked', 'search_view_changed')
        expected_next = self.page+1 if self.page+1 < PAGES else None
        if (self.done or (r.target, r.range, r.cone_degrees, r.page) != (self.goal.target, self.goal.range, self.goal.cone_degrees, self.page)
                or r.next_page != expected_next or type(r.next_page) is bool
                or r.visited_cells != min(PAGE_SIZE, SIDE*SIDE-self.page*PAGE_SIZE)
                or r.rays_cast > r.visited_cells or len(r.matches) > r.rays_cast or abs(math.hypot(*r.forward)-1) > 1e-6):
            raise SkillStop('blocked', 'invalid_search_response')
        for hit in r.matches:
            p = hit.position; point = hit.aim_position; delta = [a-b for a,b in zip(point,r.eye_position)]
            distance = math.hypot(*delta)
            if (not (hit.id in LOGS if self.goal.target == 'logs' else hit.id == self.goal.target)
                    or abs(p[0]) > 29_999_984 or abs(p[2]) > 29_999_984 or not -2048 <= p[1] <= 2048
                    or distance > self.goal.range+.001 or distance <= 0
                    or abs(distance-hit.distance_blocks) > .001
                    or abs(math.dist(r.eye_position,[v+.5 for v in p])-hit.eye_distance_to_center) > .001
                    or sum(a*b for a,b in zip(delta,r.forward))/distance < math.cos(math.radians(self.goal.cone_degrees/2)) - 1e-6):
                raise SkillStop('blocked', 'invalid_search_response')
            key = tuple(p)
            if key in self.rows and self.rows[key]['id'] != hit.id:raise SkillStop('blocked', 'search_scene_changed')
            if key not in self.rows:
                if len(self.rows) < MAX_MATCHES:self.rows[key] = hit.model_dump(mode='json')
                else:self.limited = True
        self.pose, self.view = pose, r.view_id
        if self.first_ms is None:self.first_ms = r.sampled_at_ms
        self.last_ms = r.sampled_at_ms; self.cells += r.visited_cells; self.rays += r.rays_cast
        self.complete = r.next_page is None; self.limited |= r.truncated or (len(self.rows) >= MAX_MATCHES and not self.complete)
        self.done = self.complete or self.limited; self.page += 1

    def result(self):
        if not self.done:raise ValueError('Incomplete search has no result')
        found = bool(self.rows)
        return SkillResult(status='succeeded' if found else 'blocked', reason='targets_observed' if found else 'target_not_seen',
            text='Matching first-hit surfaces observed; no reach/path proof.' if found else 'No matching sampled surface. This does NOT prove absence; choose further observations or exploration yourself.',
            details={'profile': PROFILE, 'target': self.goal.target, 'range': self.goal.range, 'cone_degrees': self.goal.cone_degrees,
                     'actor_session': self.actor, 'view_id': self.view, 'eye_position': self.pose[0], 'forward': self.pose[1],
                     'matches': list(self.rows.values()), 'pages_read': self.page, 'grid_cells': SIDE*SIDE,
                     'visited_cells': self.cells, 'rays_cast': self.rays, 'scan_complete': self.complete,
                     'result_limit_reached': self.limited, 'sampled_from_ms': self.first_ms, 'sampled_to_ms': self.last_ms,
                     'partial_visibility': True, 'absence_proven': False, 'pixel_visibility_verified': False,
                     'atomic_snapshot': False, 'cached': False, 'distance_reference': 'eye_to_observed_surface',
                     'limits': 'Native outline/fluid rays, not renderer pixels. Transparency, small exposed patches, entities and between-ray gaps remain unsupported/incomplete.'})


def search(context, goal):
    context.check(); scene = context.player.observe(); context.check()
    if scene.get('search_supported') is not True:raise SkillStop('blocked', 'search_mod_upgrade_required')
    if not scene.get('in_world') or not scene.get('alive'):raise SkillStop('blocked', 'live_player_required')
    scan = SearchScan(goal, scene.get('actor_session'))
    while not scan.done:
        context.check()
        result = context.player.search_page(**scan.request(), actor_session=scan.actor)
        context.check(); scan.accept(result)
        context.publish({'phase': 'search', 'pages_read': scan.page, 'matches': len(scan.rows)})
        if not scan.done:context.pause(.01)
    context.check(); return scan.result()


async def search_async(fetch, goal, actor, check=lambda: None):
    try:
        scan = SearchScan(goal, actor)
        async with asyncio.timeout(goal.timeout_seconds):
            while not scan.done:
                check(); raw = await fetch(scan.request()); check(); scan.accept(raw)
                if not scan.done:await asyncio.sleep(.01)
            check(); return scan.result()
    except SkillStop as stop:
        return SkillResult(status=stop.status, reason=stop.reason, text=stop.reason.replace('_', ' '))
    except NativeOperationError as error:
        return SkillResult(status='blocked', reason=str(error), text='Native search precondition changed; no automatic retry.')
    except TimeoutError:
        return SkillResult(status='timed_out', reason='search_deadline', text='Search incomplete; no absence or reach proof. No automatic retry.')


SEARCH = SkillDefinition('search',
    'Targeted READ-ONLY search using additional native rays, not the look_around cache. '
    'Exact block ID or logs; fixed 65x65 cone grid, at most 34 bounded pages and 32 matches. '
    'No centre hit needed, no turning/walking/mining. Changed actor/view aborts. '
    'No matches means not seen, never proof of absence. Native shapes, NOT exact renderer pixels.',
    Search, search, controls_player=False)
