import bpy
from bpy.types import ID, Material, NodeTree, Object


class DetachedMaterials:
	"""Copies of the materials and node groups the clean meshes use, cut loose from the rest of the file:
	drivers and object inputs reach into it (a toon shader's light empty, tied to the rig with all its widgets),
	so the saved shading keeps its current values without them."""

	def __init__(self) -> None:
		self.materials: dict[Material, Material] = {}
		self.trees: dict[NodeTree, NodeTree] = {}

	def swap(self, obj: Object) -> None:
		"""Give the mesh the detached copies of its materials."""
		slots = obj.data.materials
		for i, material in enumerate(slots):
			if material is not None:
				slots[i] = self._material(material)

	def standing_in(self) -> dict[ID, ID]:
		"""{copy: original} for every copy made."""
		return {
			copy: original
			for original, copy in [*self.materials.items(), *self.trees.items()]
		}

	def remove(self) -> None:
		for material in self.materials.values():
			bpy.data.materials.remove(material)
		for tree in self.trees.values():
			bpy.data.node_groups.remove(tree)

	def _material(self, material: Material) -> Material:
		if material not in self.materials:
			copy = material.copy()
			if copy.animation_data:
				copy.animation_data_clear()
			if copy.node_tree is not None:
				self._detach(copy.node_tree)
			self.materials[material] = copy
		return self.materials[material]

	def _detach(self, tree: NodeTree) -> None:
		if tree.animation_data:
			tree.animation_data_clear()
		for node in tree.nodes:
			if isinstance(getattr(node, "object", None), Object):
				node.object = None
			if node.type == "GROUP" and node.node_tree is not None:
				node.node_tree = self._tree(node.node_tree)

	def _tree(self, tree: NodeTree) -> NodeTree:
		if tree not in self.trees:
			self.trees[tree] = tree.copy()
			self._detach(self.trees[tree])
		return self.trees[tree]
