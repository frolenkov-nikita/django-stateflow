from django.db import models
from django import forms
from importlib import import_module

from .stateclass import DjangoState, Flow



class SubfieldBase(type):
    """
    A metaclass for custom Field subclasses. This ensures the model's attribute
    has the descriptor protocol attached to it.
    """
    def __new__(cls, name, bases, attrs):
        new_class = super(SubfieldBase, cls).__new__(cls, name, bases, attrs)
        new_class.contribute_to_class = make_contrib(
            new_class, attrs.get('contribute_to_class')
        )
        return new_class


class Creator(object):
    """
    A placeholder class that provides a way to set the attribute on the model.
    """
    def __init__(self, field):
        self.field = field

    def __get__(self, obj, type=None):
        if obj is None:
            return self
        return obj.__dict__[self.field.name]

    def __set__(self, obj, value):
        obj.__dict__[self.field.name] = self.field.to_python(value)


def make_contrib(superclass, func=None):
    """
    Returns a suitable contribute_to_class() method for the Field subclass.
    If 'func' is passed in, it is the existing contribute_to_class() method on
    the subclass and it is called before anything else. It is assumed in this
    case that the existing contribute_to_class() calls all the necessary
    superclass methods.
    """
    def contribute_to_class(self, cls, name, **kwargs):
        if func:
            func(self, cls, name, **kwargs)
        else:
            super(superclass, self).contribute_to_class(cls, name, **kwargs)
        setattr(cls, self.name, Creator(self))

    return contribute_to_class


class StateWidget(forms.Select):

    def render_options(self, choices, selected_choices):
        from itertools import chain
        from django.utils.encoding import force_unicode
        from django.utils.html import escape, conditional_escape
        def render_option(option_value, option_label):
            option_value = force_unicode(option_value)
            selected_html = (option_value in selected_choices) \
                and ' selected="selected"' or ''
            return '<option value="%s"%s>%s</option>' % (
                escape(option_value), selected_html,
                conditional_escape(force_unicode(option_label)))
        # Normalize to strings.
        selected_choices = [
            v.get_value()
            for v in selected_choices if isinstance(v, DjangoState)]
        selected_choices = set([force_unicode(v) for v in selected_choices])
        output = []
        for option_value, option_label in chain(self.choices, choices):
            if isinstance(option_label, (list, tuple)):
                output.append('<optgroup label="%s">' %
                              escape(force_unicode(option_value)))
                for option in option_label:
                    output.append(render_option(*option))
                output.append('</optgroup>')
            else:
                output.append(render_option(option_value, option_label))
        return '\n'.join(output)


def load_flow(flow_path):
    dot = flow_path.rindex('.')
    mod_name, cls_name = flow_path[:dot], flow_path[dot+1:]
    mod = import_module(mod_name)
    flow = getattr(mod, cls_name)
    return flow


def resolve_flow(flow_name):
    try:
        flow_is_cls = issubclass(flow_name, Flow)
    except:
        flow_is_cls = False
    if flow_is_cls:
        return flow_name, str(flow_name)
    else:
        return load_flow(flow_name), flow_name


class StateFlowField(models.Field, metaclass=SubfieldBase):
    def __init__(self, verbose_name=None, name=None,
                 flow=None, **kwargs):
        if flow is None:
            raise ValueError("StateFlowField need to have defined flow")
        self._flow_kwarg = flow  # for deconstruct
        self.flow, self.flow_path = resolve_flow(flow)
        models.Field.__init__(self, verbose_name, name, **kwargs)

    def get_internal_type(self):
        return "CharField"

    def get_prep_value(self, value):
        if value is None:
            return None
        elif isinstance(value, type) and issubclass(value, DjangoState):
            return value.get_value()
        else:
            return str(value)

    def from_db_value(self, value, expression, connection, context):
        return self.to_python(value)

    def to_python(self, value):
        if isinstance(value, type) and issubclass(value, DjangoState):
            return value
        return self.flow.get_state(value)

    def formfield(self, **kwargs):
        choices = [(None, '----')] + self.flow.state_choices()
        return forms.ChoiceField(choices=choices, widget=StateWidget)

    def deconstruct(self):
        name, path, args, kwargs = super(StateFlowField, self).deconstruct()
        kwargs['flow'] = self._flow_kwarg
        return name, path, args, kwargs
