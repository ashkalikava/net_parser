import pathlib
import re
import timeit
from typing import Union, List
from net_parser.utils import get_logger, load_text, first_candidate_or_none
from net_parser.config import BaseConfigLine

re._MAXCACHE = 1024


class BaseConfigParser(object):

    PATTERN_TYPE = type(re.compile(pattern=""))

    def __init__(self, config: Union[pathlib.Path, List[str], str], verbosity: int = 4, name: str = "BaseConfigParser", **kwargs):
        """
        Base class for parsing Cisco-like configs

        Args:
            config (:obj:`pathlib.Path` or `str` or `list`): Config file in a form of `pathlib.Path`, or `string`
                containing the entire config or list of lines of the config file
            verbosity (:obj:`int`, optional): Determines the verbosity of logging output, defaults to 4: Info

        Attributes:
            lines (list): Contains list of all config lines stored as objects (see :class:`ccutils.ccparser.BaseConfigLine`)
            config_lines_str (list): Contains list of all config lines stored as strings

        Examples:

            Possible config inputs::

                # Using pathlib
                config_file = pathlib.Path("/path/to/config_file.txt")
                config = BaseConfigParser(config=config_file)

                # Using string
                config_string = '''
                hostname RouterA
                !
                interface Ethernet0/0
                 description Test Interface
                 ip address 10.0.0.1 255.255.255.0
                !
                end
                '''
                config = BaseConfigParser(config=config_string)

                # Using list
                config_list = [
                "hostname RouterA",
                    "!",
                    "interface Ethernet0/0",
                    " description Test Interface",
                    " ip address 10.0.0.1 255.255.255.0",
                    "!",
                    "end"
                ]
                config = BaseConfigParser(config=config_list)

        """
        self.verbosity = verbosity
        self.logger = get_logger(name=name, verbosity=verbosity)
        self._config = config
        self.lines = []

    def load_config(self) -> List[str]:
        raw_lines = load_text(obj=self._config, logger=self.logger)
        return raw_lines

    def parse(self):
        """
        Entry function which triggers the parsing process. Called automatically when instantiating the object.

        :return: ``None``
        """
        raw_config_lines = self.load_config()
        self.config_lines_str = raw_config_lines
        self._create_cfg_line_objects()

    def _check_path(self, filepath):
        path = None
        if not isinstance(filepath, pathlib.Path):
            path = pathlib.Path(filepath)
        else:
            path = filepath
        path = path.resolve()
        if not path.exists():
            self.logger.error(msg="Path '{}' does not exist.".format(filepath))
            return None
        if not path.is_file():
            self.logger.error(msg="Path '{}' is not a file.".format(filepath))
        if not path.is_absolute():
            path = path.resolve()
            self.logger.debug("Path '{}' is existing file.".format(filepath))
            return path
        else:
            self.logger.debug("Path '{}' is existing file.".format(filepath))
            return path

    def _get_indent(self, line):
        indent_size = len(line) - len(line.lstrip(" "))
        return indent_size

    def _get_clean_config(self, first_line_regex=r"^version \d+\.\d+", last_line_regex=r"^end"):
        self.logger.debug(msg="Cleaning config lines")
        first_regex = re.compile(pattern=first_line_regex, flags=re.MULTILINE)
        last_regex = re.compile(pattern=last_line_regex, flags=re.MULTILINE)
        first = None
        last = None
        for i in range(len(self.config_lines_str)):
            if not first:
                if re.match(pattern=first_regex, string=all_lines[i]):
                    first = i
                    self.logger.debug(msg="Found first config line: '{}'".format(all_lines[first]))
            if not last:
                if re.match(pattern=last_regex, string=all_lines[i]):
                    last = i
                    self.logger.debug(msg="Found last config line: '{}'".format(all_lines[last]))
                    break
        if not first or not last:
            self.config_lines_str = []
            self.logger.error(msg="No valid config found!")
        else:
            self.config_lines_str = all_lines[first:last + 1]
            self.logger.info(msg="Loading {} config lines.".format(len(self.config_lines_str)))
        # Fix indent

    def fix_indents(self):
        """
        Function for fixing the indentation level of config lines.

        :return:
        """
        indent_map = list(map(self._get_indent, self.config_lines_str))
        fixed_indent_map = []
        for i in range(len(indent_map)):
            if i == 0:
                ### Assume the first line is not indented
                fixed_indent_map.append(0)
                continue
            if indent_map[i] == 0:
                fixed_indent_map.append(0)
                continue
            # If indent is same preceding line, copy its indent
            if indent_map[i] == indent_map[i-1]:
                fixed_indent_map.append(fixed_indent_map[-1])
            # If indent is higher that preceding line, increase by one
            elif indent_map[i] > indent_map[i-1]:
                fixed_indent_map.append(fixed_indent_map[-1]+1)
            # If indent is lower that preceding l
            elif indent_map[i] < indent_map[i-1]:
                fixed_indent_map.append(fixed_indent_map[-1]-1)
        for i, val in enumerate(fixed_indent_map):
            self.config_lines_str[i] = " "*val + self.config_lines_str[i].strip()
            #print(val, "'{}'".format(self.config_lines_str[i]))

    def _create_cfg_line_objects(self):
        """
        Function for generating ``self.lines``.

        """
        start = timeit.default_timer()
        for number, text in enumerate(self.config_lines_str):
            if re.match(pattern=r"^interface\s\S+", string=text, flags=re.MULTILINE):
                self.lines.append(self.INTERFACE_LINE_CLASS(number=number, text=text, config=self, verbosity=self.verbosity).return_obj())
            else:
                self.lines.append(BaseConfigLine(number=number, text=text, config=self, verbosity=self.verbosity).return_obj())
        for line in self.lines:
            line.type = line.get_type
        self.logger.debug(msg="Created {} ConfigLine objects in {} ms.".format(len(self.lines), (timeit.default_timer()-start)*1000))

    def _compile_regex(self, regex, flags=re.MULTILINE):
        """
        Helper function for compiling `re` patterns from string.

        :param str regex: Regex string
        :param flags: Flags for regex pattern, default is re.MULTILINE
        :return:
        """
        pattern = None
        try:
            pattern = re.compile(pattern=regex, flags=flags)
        except Exception as e:
            self.logger.error(msg="Error while compiling regex '{}'. Exception: {}".format(regex, repr(e)))
        return pattern

    def find_objects(self, regex, flags=re.MULTILINE, group: Union[int, str, None] = None):
        """
        Function for filtering Config Lines Objects based on given regex.

        Args:
            regex (:obj:`re.Pattern` or `str`): Regex based on which the search is done
            flags (:obj:`int`, optional): Set custom flags for regex, defaults to ``re.MULTILINE``

        Examples:

            Example::

                # Initialize the object
                config = BaseConfigParser(config="/path/to/config_file.cfg")

                # Define regex for matching config lines
                interface_regex = r"^ interface"

                # Apply the filter
                interface_lines = config.find_objects(regex=interface_regex)

                # Returns subset of ``self.lines`` which match specified regex

        """
        pattern = None
        if not isinstance(regex, self.PATTERN_TYPE):
            pattern = self._compile_regex(regex=regex, flags=flags)
        else:
            pattern = regex
        lines = []
        results = []
        for line in self.lines:
            result = line.re_search(regex=pattern, group=group)
            if result:
                lines.append(line)
                results.append(result)
        if group is None:
            results = list(lines)
        else:
            return results
        self.logger.debug(msg="Matched {} lines for query '{}'".format(len(results), regex))
        return results

    def get_section_by_parents(self, parents):
        if not isinstance(parents, list):
            parents = list(parents)
        section = list(self.lines)
        for parent in parents:
            section = [x.get_children() for x in section if bool(x.is_parent and x.re_match(parent))]
            if len(section) == 1:
                section = section[0]
            elif len(section) > 1:
                self.logger.error("Multiple lines matched parent statement. Cannot determine config section.")
                return []
            else:
                self.logger.error("No lines matched parent statement. Cannot determine config section.")
                return []
        return section

    def match_to_dict(self, line, patterns):
        """

        Args:
            line: Instance of `BaseConfigLine` object
            patterns: List of compiled `re` patterns
            minimal_result: Bool, if True, omits keys with value `None`

        Returns:
            dict: Dictionary containing named groups across all provided patterns

        """
        entry = {}

        for pattern in patterns:
            match_result = line.re_search(regex=pattern, group="ALL")
            if match_result is not None:
                entry.update(match_result)
            else:
                if self.minimal_results:
                    continue
                else:
                    entry.update({k: None for k in pattern.groupindex.keys()})
        return entry

    def property_autoparse(self, candidate_pattern, patterns):
        """
        Function for searching multiple patterns across all occurrences of lines that matched candidate_pattern
        Args:
            candidate_pattern:
            patterns:

        Returns:

        """
        properties = None
        candidates = self.find_objects(regex=candidate_pattern)
        if len(candidates):
            properties = []
        else:
            return properties
        for candidate in candidates:
            properties.append(self.match_to_dict(line=candidate, patterns=patterns))
        return properties

    def section_property_autoparse(self, parent, patterns, return_with_line=False):
        entries = None
        if isinstance(parent, BaseConfigLine):
            candidates = [parent]
        elif isinstance(parent, (str, self.PATTERN_TYPE)):
            candidates = self.find_objects(regex=parent)
        if len(candidates):
            entries = []
        else:
            return entries
        for candidate in candidates:
            entry = {}
            if isinstance(parent, (str, self.PATTERN_TYPE)):
                entry.update(self.match_to_dict(line=candidate, patterns=[parent]))
            for pattern in patterns:
                updates = candidate.re_search_children(regex=pattern, group="ALL")
                if len(updates) == 1:
                    entry.update(updates[0])
                elif len(updates) == 0:
                    if self.minimal_results:
                        continue
                    else:
                        entry.update({k: None for k in pattern.groupindex.keys()})
                else:
                    self.logger.warning("Multiple possible updates found for Pattern: '{}' on Candidate: '{}'".format(pattern, candidate))
            if return_with_line:
                entries.append((candidate, entry))
            else:
                entries.append(entry)
        return entries

    def first_candidate_or_none(self, candidates: list, wanted_type=None):
        return first_candidate_or_none(candidates=candidates, logger=self.logger, wanted_type=wanted_type)
