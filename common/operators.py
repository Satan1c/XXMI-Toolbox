from bpy.types import Context, Object, Operator

from .utils import ToolError, object_mode, selected_meshes


def report_results(operator: Operator, done: str, errors: list[str]) -> None:
	for error in errors:
		operator.report({"ERROR"}, error)
	if done and not errors:
		operator.report({"INFO"}, done)


class PerMeshOperator:
	bl_options = {"REGISTER", "UNDO"}

	@classmethod
	def poll(cls, context: Context) -> bool:
		return bool(selected_meshes(context))

	def process(self, context: Context, obj: Object) -> None:
		raise NotImplementedError

	def summary(self, count: int) -> str:
		return f"{self.bl_label}: {count} objects"

	def execute(self, context: Context) -> set[str]:
		errors, count = [], 0
		with object_mode(context):
			for obj in selected_meshes(context):
				try:
					self.process(context, obj)
					count += 1
				except ToolError as e:
					errors.append(str(e))
		report_results(self, self.summary(count), errors)
		# Not CANCELLED: other objects may already be changed and need an undo step.
		return {"FINISHED"}
