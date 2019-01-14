import builtins
import inspect
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable, Dict, Union

from mypy_extensions import _TypedDictMeta  # type: ignore

from py_codegen.type_extractor.nodes.DictFound import DictFound
from py_codegen.type_extractor.nodes.ListFound import ListFound
from py_codegen.type_extractor.nodes.TypedDictFound import TypedDictFound
from py_codegen.type_extractor.nodes.ClassFound import ClassFound
from py_codegen.type_extractor.errors import (
    DuplicateNameFound,
)
from py_codegen.type_extractor.nodes.FunctionFound import FunctionFound
from .TypeOR import TypeOR


def is_builtin(something):
    return inspect.getmodule(something) is builtins


class TypeExtractor:
    functions: Dict[str, FunctionFound]
    classes: Dict[str, ClassFound]

    def __init__(self):
        self.functions = dict()
        self.classes = dict()

    def add_function(self, options):
        def add_function_decoration(func: Callable):
            signature = inspect.getfullargspec(func)
            self.__process_params(signature.annotations)
            function_found = self.__to_function_found(func)
            if function_found.name in self.functions:
                raise DuplicateNameFound(
                    self.functions.get(
                        function_found.name
                    ),
                    function_found
                )
            self.functions[function_found.name] = function_found
            return func
        return add_function_decoration

    def __process_params(self, params: Dict[str, Union[type, None]]):
        processed_params = {
            key: self.__process_param(value)
            for key, value in params.items()
        }
        return processed_params

    def __process_param(self, typ):

        if is_builtin(typ):
            return typ

        elif isinstance(typ, _TypedDictMeta):
            annotations = {
                key: self.__process_param(value)
                for key, value in typ.__annotations__.items()
            }
            return TypedDictFound(
                annotations=annotations,
                name=typ.__qualname__,
                raw=typ,
            )

        elif inspect.isfunction(typ):
            function_found = self.__to_function_found(typ)
            return function_found

        elif inspect.isclass(typ):
            class_found = self.__to_class_found(typ)
            self.__add_class_found(class_found)
            return class_found

        try:
            if typ.__origin__ is list:
                return self.__process_list(typ)
            if typ.__origin__ is Union:
                return self.__process_union(typ)
            if typ.__origin__ is dict:
                return self.__process_dict(typ)
        except:
            pass

        raise NotImplementedError(f'type_extractor not implemented for {typ}')

    def __process_dict(self, dict_typ):
        assert(dict_typ.__origin__ is dict)
        processed_key_typ = self.__process_param(dict_typ.__args__[0])
        processed_value_typ = self.__process_param(dict_typ.__args__[1])
        return DictFound(
            key=processed_key_typ,
            value=processed_value_typ,
        )

    def __process_list(self, list_typ):
        assert(list_typ.__origin__ is list)
        processed_typ = self.__process_param(list_typ.__args__[0])
        return ListFound(typ=processed_typ)

    def __process_union(self, union):
        assert(union.__origin__ is Union)
        types = union.__args__
        type_a = self.__process_param(types[0])
        type_b = self.__process_param(types[1])
        return TypeOR(
            a=type_a,
            b=type_b,
        )

    def __to_class_found(self, _class):
        _data_class = dataclass(_class)
        argspec = inspect.getfullargspec(_data_class)
        module = inspect.getmodule(_class)
        filename = module.__file__
        fields_to_process = deepcopy(argspec.annotations)
        unwanted_keys = set(fields_to_process.keys()) - set(argspec.args)
        for unwanted_key in unwanted_keys:
            del fields_to_process[unwanted_key]
        fields = self.__process_params(fields_to_process)
        class_found = ClassFound(
            name=_class.__name__,
            class_raw=_class,
            filePath=filename,
            raw_fields=argspec.annotations,
            fields=fields,
            doc=_class.__doc__
        )
        return class_found

    def __to_function_found(self, func: Callable) -> FunctionFound:
        argspec = inspect.getfullargspec(func)
        signature = inspect.signature(func)
        module = inspect.getmodule(func)
        filename = module.__file__
        params = self.__process_params(argspec.annotations)
        return_type = self.__process_param(signature.return_annotation)
        func_found = FunctionFound(
            name=func.__name__,
            filePath=filename,
            raw_params=argspec.annotations,
            params=params,
            doc=func.__doc__ or '',
            func=func,
            return_type=return_type,
        )
        return func_found

    def __add_class_found(self, class_found: ClassFound):
        self.classes[class_found.name] = class_found

    def add_class(self, options):
        def add_class_decoration(_class):
            if is_builtin(_class):
                return
            class_found = self.__to_class_found(_class)
            self.__add_class_found(class_found)
        return add_class_decoration
