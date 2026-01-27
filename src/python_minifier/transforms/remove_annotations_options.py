from dataclasses import dataclass


@dataclass(frozen=True)
class RemoveAnnotationsOptions:
    """
    Options for the RemoveAnnotations transform

    This can be passed to the minify function as the remove_annotations argument

    :param remove_variable_annotations: Remove variable annotations
    :type remove_variable_annotations: bool
    :param remove_return_annotations: Remove return annotations
    :type remove_return_annotations: bool
    :param remove_argument_annotations: Remove argument annotations
    :type remove_argument_annotations: bool
    :param remove_class_attribute_annotations: Remove class attribute annotations
    :type remove_class_attribute_annotations: bool
    :param aggressively_minify_class_attributes: Aggressively minify class attribute annotations (may break code)
    :type aggressively_minify_class_attributes: bool
    """

    remove_variable_annotations: bool = True
    remove_return_annotations: bool = True
    remove_argument_annotations: bool = False
    remove_class_attribute_annotations: bool = False
    aggressively_minify_class_attributes: bool = False

    def __repr__(self):
        return (
            "RemoveAnnotationsOptions(remove_variable_annotations=%r, remove_return_annotations=%r, remove_argument_annotations=%r, remove_class_attribute_annotations=%r)"
            % (
                self.remove_variable_annotations,
                self.remove_return_annotations,
                self.remove_argument_annotations,
                self.remove_class_attribute_annotations,
            )
        )

    def __nonzero__(self):
        return any(
            (
                self.remove_variable_annotations,
                self.remove_return_annotations,
                self.remove_argument_annotations,
                self.remove_class_attribute_annotations,
            )
        )

    def __bool__(self):
        return self.__nonzero__()
