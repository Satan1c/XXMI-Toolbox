from collections.abc import Iterator
from contextlib import contextmanager

import bpy
import numpy as np
from bpy.types import ArmatureEditBones, Context, Object
from mathutils import Matrix, Vector

from ..common.library import GAME_ARMATURE_KEY
from ..common.log import log
from ..common.transfer import joined_source
from ..common.utils import ToolError, follow, world_positions
from ..vertex_groups.ids import vg_id
from ..vertex_groups.remap import overlaps
from ..vertex_groups.weights import read_weights

# {ID: centre of the dumped vertices it weighs, in the ID armature's space}:
# lets a saved game armature take new dumped meshes without the game meshes.
CENTRES_KEY = "XXMI_Toolbox:Centres"
# Recorded and new centres closer than this share of the dump's size are the same group.
SAME_PLACE = 0.02
# Share of the IDs two meshes both use that must land on the same game bones for them to share an ID space.
SAME_SPACE = 0.9
# Mean distance from a dumped group's centre to the nearest game bone's, relative to the dump's size, past which
# the game model isn't where the dump is.
MAX_OFFSET = 0.05
# A mirror must beat the game model's own orientation by this much: a symmetric dump can't tell them apart.
CLEAR_WIN = 0.7
_MIRROR_X = Matrix.Scale(-1.0, 4, (1.0, 0.0, 0.0))
# Bounding boxes whose sizes differ by less than this share of the dumped mesh's diagonal are the same mesh.
SAME_SIZE = 0.005


class Space:
	"""Meshes numbering their groups the same way, and the hidden armature whose bones are named by those IDs."""

	def __init__(
		self, armature: Object | None = None, bones: dict[int, str] | None = None
	) -> None:
		self.armature = armature
		self.bones = bones or {}
		self.meshes = []


def game_armature(obj: Object | None) -> Object | None:
	"""The armature a pose is given to: an ID armature stands for the game armature it follows."""
	if obj is None or obj.type != "ARMATURE":
		return None
	return obj.get(GAME_ARMATURE_KEY) or obj


def group_centres(obj: Object) -> dict[str, np.ndarray]:
	"""{group name: world-space weighted centre} of the groups with weights."""
	mesh = obj.data
	co = world_positions(obj)
	verts, groups, weights = read_weights(mesh)
	count = len(obj.vertex_groups)
	total = np.bincount(groups, weights, minlength=count)
	sums = np.stack(
		[
			np.bincount(groups, weights * co[verts, axis], minlength=count)
			for axis in range(3)
		],
		1,
	)
	return {
		vg.name: sums[vg.index] / total[vg.index]
		for vg in obj.vertex_groups
		if total[vg.index] > 0.0
	}


def _bounds(obj: Object) -> tuple[np.ndarray, np.ndarray]:
	co = world_positions(obj)
	return co.min(0), co.max(0)


def _shift(game: list[Object], dumped: list[Object]) -> Vector | None:
	"""How far the dump sits from the game model, told by dumped meshes that are a game mesh moved: a game can draw
	the character off its rig's origin (on its soles rather than its heels)."""
	game_bounds = [_bounds(obj) for obj in game if len(obj.data.vertices)]
	shifts, tolerance = [], 0.0
	for obj in dumped:
		low, high = _bounds(obj)
		size = high - low
		tolerance = max(tolerance, SAME_SIZE * float(np.linalg.norm(size)))
		shifts += [
			(low + high - game_low - game_high) / 2
			for game_low, game_high in game_bounds
			if np.abs(game_high - game_low - size).max()
			< SAME_SIZE * np.linalg.norm(size)
		]
	if not shifts:
		return None
	shifts = np.array(shifts)
	median = np.median(shifts, 0)
	# Most pairs must agree: one coincidental match in size says nothing.
	agree = np.linalg.norm(shifts - median, axis=1) < tolerance
	log.debug(
		"%d of %d same-size mesh pairs agree on the dump's offset",
		agree.sum(),
		len(shifts),
	)
	if agree.sum() * 2 <= len(shifts) or np.linalg.norm(median) < tolerance:
		return None
	return Vector(shifts[agree].mean(0))


def _move(rig: Object, game: list[Object], matrix: Matrix) -> None:
	# Children follow their parent, so only the top of the game model is moved.
	moved = {rig, *game}
	for obj in moved:
		if obj.parent not in moved:
			obj.matrix_world = matrix @ obj.matrix_world


def _align(
	rig: Object, game: list[Object], dumped: list[Object], settled: bool
) -> bool:
	"""Mirror the game model if that's how it lines up with the dump, unless earlier pieces already settled it."""
	game_centres = np.array(
		[centre for obj in game for centre in group_centres(obj).values()]
	)
	dumped_centres = np.array(
		[centre for obj in dumped for centre in group_centres(obj).values()]
	)
	if not len(game_centres) or not len(dumped_centres):
		raise ToolError(
			"The game model and the dumped meshes need weighted vertex groups"
		)
	size = float(np.linalg.norm(dumped_centres.max(0) - dumped_centres.min(0))) or 1.0

	def offset(centres: np.ndarray) -> float:
		distances = np.linalg.norm(
			dumped_centres[:, None, :] - centres[None, :, :], axis=2
		)
		return float(distances.min(1).mean()) / size

	as_is = offset(game_centres)
	mirrored = float("inf") if settled else offset(game_centres * (-1.0, 1.0, 1.0))
	log.debug(
		"group centres off the game model's: %.4f as is, %.4f mirrored", as_is, mirrored
	)
	if min(as_is, mirrored) > MAX_OFFSET:
		raise ToolError(
			f"The game model doesn't line up with the dumped meshes: put {rig.name} where they are, "
			f"at the same scale"
		)
	if mirrored >= as_is * CLEAR_WIN:
		return False
	# Importers disagree on handedness.
	_move(rig, game, _MIRROR_X)
	return True


def _bone_maps(
	context: Context, rig: Object, game: list[Object], dumped: list[Object]
) -> dict[Object, dict[int, str]]:
	"""Per dumped mesh, {ID: game bone} from the game weights on the nearest game surface."""
	pose_position = rig.data.pose_position
	rig.data.pose_position = "REST"
	try:
		with joined_source(context, game) as joined:
			names, matrices = overlaps(context, dumped, joined, similarity=True)
	finally:
		rig.data.pose_position = pose_position
	maps = {}
	for obj, matrix in matrices.items():
		rows = {}
		for vg in obj.vertex_groups:
			group_id = vg_id(vg.name)
			if group_id is not None and matrix[vg.index].any():
				rows[group_id] = rows.get(group_id, 0.0) + matrix[vg.index]
		maps[obj] = {
			group_id: names[int(row.argmax())]
			for group_id, row in rows.items()
			if names[int(row.argmax())] in rig.data.bones
		}
	return maps


def existing_spaces(context: Context, rig: Object) -> list[Space]:
	spaces = []
	for obj in context.scene.objects:
		if obj.type == "ARMATURE" and obj.get(GAME_ARMATURE_KEY) == rig:
			bones = {}
			for pose_bone in obj.pose.bones:
				constraint = next(
					(c for c in pose_bone.constraints if c.type == "COPY_TRANSFORMS"),
					None,
				)
				if (
					constraint is not None
					and constraint.target == rig
					and pose_bone.name.isdigit()
				):
					bones[int(pose_bone.name)] = constraint.subtarget
			spaces.append(Space(obj, bones))
	return spaces


def _space_for(bones: dict[int, str], spaces: list[Space]) -> Space | None:
	"""The space agreeing most with the mesh's bones, or None if every one gives some shared ID another bone."""
	best, best_agree = None, -1
	for space in spaces:
		shared = [group_id for group_id in bones if group_id in space.bones]
		agree = sum(space.bones[group_id] == bones[group_id] for group_id in shared)
		if agree >= SAME_SPACE * len(shared) and agree > best_agree:
			best, best_agree = space, agree
	return best


@contextmanager
def editing(context: Context, armature: Object) -> Iterator[ArmatureEditBones]:
	# Edit mode takes every selected armature along, the game one included: only the ID armature may be selected.
	view_layer = context.view_layer
	active, hidden = view_layer.objects.active, armature.hide_get()
	selected = [obj for obj in view_layer.objects if obj.select_get()]
	for obj in selected:
		obj.select_set(False)
	armature.hide_set(False)
	armature.select_set(True)
	view_layer.objects.active = armature
	bpy.ops.object.mode_set(mode="EDIT")
	try:
		yield armature.data.edit_bones
	finally:
		bpy.ops.object.mode_set(mode="OBJECT")
		armature.select_set(False)
		armature.hide_set(hidden)
		for obj in selected:
			obj.select_set(True)
		view_layer.objects.active = active


def _build(context: Context, rig: Object, space: Space) -> Object:
	armature = space.armature
	if armature is None:
		name = f"{rig.name} IDs ({space.meshes[0].name})"
		armature = bpy.data.objects.new(name, bpy.data.armatures.new(name))
		(
			rig.users_collection[0]
			if rig.users_collection
			else context.scene.collection
		).objects.link(armature)
		armature[GAME_ARMATURE_KEY] = rig
		armature.matrix_world = rig.matrix_world
		space.armature = armature
	missing = {
		group_id: bone
		for group_id, bone in space.bones.items()
		if str(group_id) not in armature.data.bones
	}
	if missing:
		with editing(context, armature) as edit_bones:
			for group_id, name in missing.items():
				source = rig.data.bones[name]
				bone = edit_bones.new(str(group_id))
				bone.tail = (0.0, 1.0, 0.0)
				bone.matrix = source.matrix_local
				bone.length = source.length
		# Same rest pose as the game bone, so copying its world transform gives the pose without any offset.
		for group_id, name in missing.items():
			constraint = armature.pose.bones[str(group_id)].constraints.new(
				"COPY_TRANSFORMS"
			)
			constraint.target, constraint.subtarget = rig, name
	return armature


def record_centres(space: Space) -> None:
	armature = space.armature
	inverse = armature.matrix_world.inverted()
	stored = dict(armature.get(CENTRES_KEY, {}))
	for obj in space.meshes:
		for name, centre in group_centres(obj).items():
			group_id = vg_id(name)
			if group_id in space.bones:
				stored.setdefault(str(group_id), list(inverse @ Vector(centre)))
	armature[CENTRES_KEY] = stored


def _recorded_centres(spaces: list[Space]) -> dict[Space, dict[int, Vector]]:
	"""Per saved ID armature, {ID: its recorded group centre, in world space}."""
	return {
		space: {
			int(key): space.armature.matrix_world @ Vector(value)
			for key, value in space.armature.get(CENTRES_KEY, {}).items()
		}
		for space in spaces
	}


def _place_tolerance(recorded: dict[Space, dict[int, Vector]]) -> float:
	"""How near a centre must be to a recorded one to be the same group: a share of the recorded dump's size."""
	points = np.array([p for centres in recorded.values() for p in centres.values()])
	size = float(np.linalg.norm(points.max(0) - points.min(0)))
	return SAME_PLACE * (size or 1.0)


def _saved_space(
	centres: dict[int, Vector],
	recorded: dict[Space, dict[int, Vector]],
	tolerance: float,
) -> Space | None:
	"""The saved ID armature whose recorded centres most of the mesh's group centres sit on."""
	best, best_close = None, 0
	for space, known in recorded.items():
		shared = [group_id for group_id in centres if group_id in known]
		close = sum(
			(centres[group_id] - known[group_id]).length < tolerance
			for group_id in shared
		)
		if shared and close >= SAME_SPACE * len(shared) and close > best_close:
			best, best_close = space, close
	return best


def _attach_saved(rig: Object, dumped: list[Object], spaces: list[Space]) -> list[str]:
	"""Attach dumped meshes to the saved ID armature whose recorded centres they share."""
	recorded = _recorded_centres(spaces)
	tolerance = _place_tolerance(recorded)

	attached, unmatched, unknown = 0, [], 0
	for obj in dumped:
		centres = {
			vg_id(name): Vector(centre) for name, centre in group_centres(obj).items()
		}
		space = _saved_space(centres, recorded, tolerance)
		log.debug(
			"%s: %d groups, on %s",
			obj.name,
			len(centres),
			space and space.armature.name,
		)
		if space is None:
			unmatched.append(obj.name)
			continue
		unknown += sum(group_id not in space.bones for group_id in centres)
		follow(obj, space.armature)
		attached += 1

	for space in spaces:
		space.armature.hide_set(True)

	lines = [f"{attached} meshes follow {rig.name} through its saved ID armatures"]
	if unmatched:
		lines.append(f"no saved ID armature fits {', '.join(sorted(unmatched))}")
	if unknown:
		lines.append(
			f"{unknown} vertex groups have IDs the saved armature has no bone for: attach them with the game model"
		)
	return lines


def _numbered(obj: Object) -> bool:
	"""Whether the mesh has vertex groups named by ID, as dumped meshes do."""
	return any(vg_id(vg.name) is not None for vg in obj.vertex_groups)


def attach(context: Context, rig: Object, dumped: list[Object]) -> list[str]:
	game = [
		obj
		for obj in context.scene.objects
		if obj.type == "MESH" and obj.find_armature() == rig
	]
	if not game:
		spaces = existing_spaces(context, rig)
		numbered = [obj for obj in dumped if _numbered(obj)]
		if numbered and any(space.armature.get(CENTRES_KEY) for space in spaces):
			return _attach_saved(rig, numbered, spaces)
		raise ToolError(
			f"No meshes are deformed by {rig.name}: import the game model with its meshes"
		)
	dumped = [obj for obj in dumped if obj not in game and _numbered(obj)]
	if not dumped:
		raise ToolError(
			"Select the dumped meshes too: meshes with numbered vertex groups"
		)
	spaces = existing_spaces(context, rig)
	# Moving the game model once pieces follow it would move them too.
	shift = None if spaces else _shift(game, dumped)
	if shift is not None:
		_move(rig, game, Matrix.Translation(shift))
		context.view_layer.update()
	mirrored = _align(rig, game, dumped, settled=bool(spaces))
	maps = _bone_maps(context, rig, game, dumped)
	known = len(spaces)
	unmatched = []
	# Largest first, so a component's main mesh sets its space before its smaller pieces are compared with it.
	for obj in sorted(dumped, key=lambda obj: -len(maps[obj])):
		if not maps[obj]:
			unmatched.append(obj.name)
			continue
		space = _space_for(maps[obj], spaces)
		if space is None:
			space = Space()
			spaces.append(space)
		for group_id, bone in maps[obj].items():
			space.bones.setdefault(group_id, bone)
		space.meshes.append(obj)
		log.debug(
			"%s: %d IDs on game bones, sharing space %d",
			obj.name,
			len(maps[obj]),
			spaces.index(space),
		)

	for space in spaces:
		if not space.meshes:
			continue
		armature = _build(context, rig, space)
		armature.hide_set(True)
		for obj in space.meshes:
			follow(obj, armature)
		record_centres(space)

	attached = sum(len(space.meshes) for space in spaces)
	lines = [
		f"{attached} meshes follow {rig.name} through {sum(bool(space.meshes) for space in spaces)} ID armatures"
		f" ({len(spaces) - known} new)"
	]
	if shift is not None:
		lines.append(
			f"moved {rig.name} and its meshes by ({shift.x:.4f}, {shift.y:.4f}, {shift.z:.4f}) to match the dump"
		)
	if mirrored:
		lines.append(f"mirrored {rig.name} and its meshes to match the dump")
	if unmatched:
		lines.append(f"no game bones under {', '.join(sorted(unmatched))}")
	return lines
