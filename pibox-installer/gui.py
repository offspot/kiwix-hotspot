from collections import OrderedDict
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, GObject
from backend.catalog import YAML_CATALOGS
from backend.content import get_expanded_size, get_collection, get_required_image_size, get_content, isremote
from run_installation import run_installation
import pytz
import tzlocal
import os
import sys
import json
import tempfile
import threading
from util import CancelEvent, ProgressHelper
import sd_card_info
from version import get_version_str
from util import human_readable_size, ONE_GB, ONE_MiB
from util import get_free_space_in_dir
from util import relpathto
from util import b64encode, b64decode
import data
import langcodes
import string
import humanfriendly
import webbrowser

VALID_RGBA = Gdk.RGBA(0., 0., 0., 0.)
INVALID_RGBA = Gdk.RGBA(1, 0.5, 0.5, 1.)
mainloop = None

def quit(*args, **kwargs):
    global mainloop
    mainloop.quit()

def run():
    global mainloop
    mainloop = GObject.MainLoop()
    try:
        mainloop.run()
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt, exiting.")
        quit()

class ShortDialog(Gtk.Dialog):
    def __init__(self, parent, buttons, msg):
        Gtk.Dialog.__init__(self, "kiwix-plug installer", parent, 0, buttons)
        self.set_default_size(150, 100)
        label = Gtk.Label(msg)
        box = self.get_content_area()
        box.add(label)
        self.show_all()

def hide_on_delete(widget, event):
    widget.hide()
    return True

class Logger(ProgressHelper):
    def __init__(self, component):
        super(Logger, self).__init__()
        self.component = component

        self.text_buffer = self.component.run_text_view.get_buffer()
        self.step_tag = self.text_buffer.create_tag("step", foreground="blue")
        self.err_tag = self.text_buffer.create_tag("err", foreground="red")
        self.succ_tag = self.text_buffer.create_tag("succ", foreground="green")
        self.stg_tag = self.text_buffer.create_tag("stg", foreground="purple")
        self.run_pulse()

    def step(self, step):
        GLib.idle_add(self.main_thread_step, step)

    def err(self, err):
        GLib.idle_add(self.main_thread_err, err)

    def raw_std(self, std):
        GLib.idle_add(self.main_thread_raw_std, std, end="")

    def std(self, std, end=None):
        GLib.idle_add(self.main_thread_std, std, end)

    def complete(self):
        GLib.idle_add(self.main_thread_complete)

    def failed(self, error):
        GLib.idle_add(self.main_thread_failed, error)

    def main_thread_text(self, text, end="\n", tag=None):
        text += end
        text_iter = self.text_buffer.get_end_iter()
        if tag is None:
            self.text_buffer.insert(text_iter, text)
        else:
            self.text_buffer.insert_with_tags(text_iter, text, tag)

    def main_thread_step(self, text):
        self.main_thread_text("--> {}".format(text), "\n", self.step_tag)
        self._update_progress_text(text)

    def main_thread_err(self, text):
        self.main_thread_text(text, "\n", self.err_tag)

    def main_thread_raw_std(self, text):
        self.main_thread_text(text)

    def main_thread_std(self, text, end=None):
        self.main_thread_text(text, end if end is not None else "\n")

    def _update_progress_text(self, text):
        self.component.run_progressbar.set_text(text)

    def update(self):
        GLib.idle_add(self.update_gui)

    def update_gui(self):
        # show text progress in console
        self.main_thread_text("[STAGE {nums}: {name} - {pc:.0f}%]"
               .format(nums=self.stage_numbers,
                       name=self.stage_name,
                       pc=self.get_overall_progress() * 100),
               tag=self.stg_tag)

        # update overall percentage on window title
        self.component.run_window.set_title(
            "Kiwix-plug installer ({:.0f}%)"
            .format(self.get_overall_progress() * 100))

        # update stage name and number (Stage x/y)
        self.component.run_step_label.set_markup(
            "<b>Stage {nums}</b>: {name}"
            .format(nums=self.stage_numbers, name=self.stage_name))

        # update the progress bar according to the stage's progress
        if self.stage_progress is not None:
            self.component.run_progressbar.set_inverted(False)
            self.component.run_progressbar.set_fraction(self.stage_progress)
        else:
            # animate the stage progress bar to show an unknown progress
            self.run_pulse()

    def main_thread_complete(self):
        super(Logger, self).complete()
        self.main_thread_text("Installation succeded.", tag=self.succ_tag)
        self.component.run_step_label.set_markup("<b>Done.</b>")
        self.progress(1)

    def main_thread_failed(self, error):
        super(Logger, self).failed()
        self.step("Failed: {}".format(error))
        self.err("Installation failed: {}".format(error))
        self.progress(1)

    def run_pulse(self):
        ''' used for progress bar animation (unknown progress) '''
        self._update_progress_text("")
        self.timeout_id = GObject.timeout_add(50, self.on_timeout)

    def on_timeout(self):
        ''' used for progress bar animation (unknown progress) '''
        if self.stage_progress is None:
            new_value = self.component.run_progressbar.get_fraction() + 0.035
            # inverse direction if end reached
            if new_value > 1:
                new_value = 0
                # switch from left-to-right to right-to-left at bounds
                self.component.run_progressbar.set_inverted(
                    not self.component.run_progressbar.get_inverted())
            self.component.run_progressbar.set_fraction(new_value)
            return True  # returns True so it continues to get called

class Component:
    def __init__(self, builder):
        self.builder = builder

    def __getattr__(self, key):
        """Allow UI builder widgets to be accessed as self.widgetname"""
        widget = self.builder.get_object(key)
        if widget:
            setattr(self, key, widget)
            return widget
        raise AttributeError(key)

def validate_label(label, condition):
    if condition:
        label.modify_bg(Gtk.StateFlags.NORMAL)
    else:
        label.modify_bg(Gtk.StateFlags.NORMAL, INVALID_RGBA.to_color())

class Application:
    def __init__(self, catalog):
        self.catalog = catalog

        builder = Gtk.Builder()
        builder.add_from_file(data.ui_glade)

        self.component = Component(builder)
        self.cancel_event = CancelEvent()
        self.logger = Logger(self.component)

        # main window
        self.component.window.connect("delete-event", quit)

        # gtk file filters (macOS fix)
        self.component.favicon_filter.set_name("Favicon (ICO, PNG)")  # opt
        self.component.favicon_filter.add_pattern("*.png")
        self.component.favicon_filter.add_pattern("*.ico")
        self.component.favicon_chooser.add_filter(
            self.component.favicon_filter)

        self.component.logo_filter.set_name("Logo (PNG)")  # opt
        self.component.logo_filter.add_pattern("*.png")
        self.component.logo_chooser.add_filter(
            self.component.logo_filter)

        self.component.css_filter.set_name("CSS File")  # opt
        self.component.css_filter.add_pattern("*.css")
        self.component.css_chooser.add_filter(
            self.component.css_filter)

        self.component.edupi_resources_filter.set_name("ZIP File")  # opt
        self.component.edupi_resources_filter.add_pattern("*.zip")
        self.component.css_chooser.add_filter(
            self.component.edupi_resources_filter)

        # menu bar
        self.component.menu_quit.connect("activate", lambda widget: self.component.window.close())
        self.component.menu_about.connect("activate", self.activate_menu_about)

        self.component.menu_load_config.connect(
            "activate", self.activate_menu_config, False)
        self.component.menu_save_config.connect(
            "activate", self.activate_menu_config, True)
        self.component.menu_help.connect(
            "activate", self.activate_menu_help)

        # wifi password
        self.component.wifi_password_switch.connect("notify::active", lambda switch, state: self.component.wifi_password_revealer.set_reveal_child(not switch.get_active()))

        # admin account
        self.component.admin_account_switch.connect("notify::active", lambda switch, state: self.component.admin_account_revealer.set_reveal_child(switch.get_active()))

        # edupi resources
        self.component.edupi_switch.connect("notify::active", lambda switch, state: self.component.edupi_resources_revealer.set_reveal_child(switch.get_active()))

        # ideascube language
        for code, language in data.ideascube_languages:
            self.component.language_tree_store.append([code, language])

        renderer = Gtk.CellRendererText()
        self.component.language_combobox.pack_start(renderer, True)
        self.component.language_combobox.add_attribute(renderer, "text", 1)

        renderer = Gtk.CellRendererText()
        self.component.timezone_combobox.pack_start(renderer, True)
        self.component.timezone_combobox.add_attribute(renderer, "text", 0)

        # output
        self.component.sd_card_combobox.connect("changed", lambda _: self.update_free_space())
        self.component.sd_card_refresh_button.connect("clicked", self.sd_card_refresh_button_clicked)
        self.component.output_stack.connect("notify::visible-child", lambda switch, state: self.update_free_space())
        self.component.size_entry.connect("changed", lambda _: self.update_free_space())

        types = [info["typ"] for info in sd_card_info.informations]
        self.component.sd_card_list_store = Gtk.ListStore(*types)
        self.component.sd_card_combobox.set_model(self.component.sd_card_list_store)

        for counter in range(0, sd_card_info.visible_informations):
            cell_renderer = Gtk.CellRendererText()
            self.component.sd_card_combobox.pack_start(cell_renderer, True)
            self.component.sd_card_combobox.add_attribute(cell_renderer, "text", counter)

        # about dialog
        self.component.about_dialog.set_logo(GdkPixbuf.Pixbuf.new_from_file_at_scale(data.pibox_logo, 200, -1, True))
        self.component.about_dialog.set_version(get_version_str())

        # done window
        self.component.done_window_ok_button.connect("clicked", lambda widget: self.component.done_window.hide())
        self.component.done_window.connect("delete-event", hide_on_delete)

        # space error window
        self.component.space_error_window_ok_button.connect("clicked", self.space_error_window_ok_button_clicked)
        self.component.space_error_window.connect("delete-event", hide_on_delete)

        # run window
        self.component.run_installation_button.connect("clicked", self.run_installation_button_clicked)
        self.component.run_window.connect("delete-event", self.run_window_delete_event)
        self.component.run_text_view.get_buffer().connect("modified-changed", self.run_text_view_scroll_down)
        self.component.run_quit_button.connect("clicked", self.run_quit_button_clicked)
        self.component.run_abort_button.connect("clicked", self.run_abort_button_clicked)
        self.component.run_copy_log_to_clipboard_button.connect("clicked", self.run_copy_log_to_clipboard_button_clicked)
        self.component.run_new_install_button.connect("clicked", self.run_new_install_button_clicked)

        # zim content
        self.component.zim_choose_content_button.connect("clicked", self.zim_choose_content_button_clicked)

        self.component.zim_list_store = Gtk.ListStore(
            str,  # key
            str,  # name
            str,  # url
            str,  # description
            str,  # formatted_size
            object,  # languages
            str,  # type
            str,  # version
            bool,  # selected
            str,  # size
            bool,  # its language is selected
            Gdk.RGBA  # background color
        )
        self.component.zim_list_store.set_sort_column_id(1, Gtk.SortType.ASCENDING)

        all_languages = set()

        for one_catalog in catalog:
            for (key, value) in one_catalog["all"].items():
                name = value["name"]
                url = value["url"]
                description = value.get("description") or "none"
                size = str(value["size"])
                languages_iso = (value.get("language") or "Unkown language").split(",")
                languages = set(map(lambda l: langcodes.Language.get(l).language_name(), languages_iso))
                typ = value["type"]
                version = str(value["version"])
                formatted_size = human_readable_size(int(size))

                self.component.zim_list_store.append([key, name, url, description, formatted_size, languages, typ, version, False, size, True, VALID_RGBA])
                all_languages |= languages

        self.component.zim_language_list_store = Gtk.ListStore(str)
        self.component.zim_language_list_store.set_sort_column_id(0, Gtk.SortType.ASCENDING)
        for language in all_languages:
            self.component.zim_language_list_store.append([language])

        # zim window
        self.component.zim_window_done_button.connect("clicked", self.zim_done_button_clicked)
        self.component.zim_window.connect("delete-event", hide_on_delete)
        self.component.zim_tree_view.connect("row-activated", self.available_zim_clicked)
        self.component.choosen_zim_tree_view.connect("row-activated", self.choosen_zim_clicked)

        ## zim window available tree view
        self.component.zim_tree_view.set_model(self.component.zim_list_store)

        renderer_text = Gtk.CellRendererText()
        column_text = Gtk.TreeViewColumn("Name", renderer_text, text=1)
        self.component.zim_tree_view.append_column(column_text)
        column_text = Gtk.TreeViewColumn("Size", renderer_text, text=4)
        self.component.zim_tree_view.append_column(column_text)
        column_text = Gtk.TreeViewColumn("Description", renderer_text, text=3)
        self.component.zim_tree_view.append_column(column_text)
        column_text.add_attribute(renderer_text, "cell_background_rgba", 11)

        zim_filter = self.component.zim_list_store.filter_new()
        zim_filter.set_visible_func(self.zim_filter_func)
        self.component.zim_tree_view.set_model(zim_filter)

        # zim window choosen tree view
        self.component.choosen_zim_tree_view.set_model(self.component.zim_list_store)

        renderer_text = Gtk.CellRendererText()
        column_text = Gtk.TreeViewColumn("Name", renderer_text, text=1)
        self.component.choosen_zim_tree_view.append_column(column_text)
        column_text = Gtk.TreeViewColumn("Size", renderer_text, text=4)
        self.component.choosen_zim_tree_view.append_column(column_text)
        column_text = Gtk.TreeViewColumn("Description", renderer_text, text=3)
        self.component.choosen_zim_tree_view.append_column(column_text)

        def get_project_size(name, lang):
            langs = ['fr', 'en'] if name == 'aflatoun' else [lang]
            return get_expanded_size(get_collection(
                **{"{}_languages".format(name): langs}))

        # kalite
        for lang, button in self.iter_kalite_check_button():
            button.set_label("{} ({})".format(button.get_label(), human_readable_size(get_project_size('kalite', lang))))
            button.connect("toggled", lambda button: self.update_free_space())

        # wikifundi
        for lang, button in self.iter_wikifundi_check_button():
            button.set_label("{} ({})".format(button.get_label(), human_readable_size(get_project_size('wikifundi', lang))))
            button.connect("toggled", lambda button: self.update_free_space())

        # aflatoun
        self.component.aflatoun_switch.connect("notify::active", lambda switch, state: self.update_free_space())
        self.component.aflatoun_label.set_label("{} ({})".format(self.component.aflatoun_label.get_label(), human_readable_size(get_project_size('aflatoun', lang))))

        # edupi
        self.component.edupi_switch.connect("notify::active", lambda switch, state: self.update_free_space())
        self.component.edupi_label.set_label("{} ({})".format(self.component.edupi_label.get_label(), human_readable_size(10 * ONE_MiB)))
        self.component.edupi_resources_url_entry.connect("changed", lambda _: self.update_free_space())
        self.component.edupi_resources_chooser.connect("file-set", lambda _: self.update_free_space())

        # language tree view
        renderer_text = Gtk.CellRendererText()
        column_text = Gtk.TreeViewColumn("Language", renderer_text, text=0)
        self.component.zim_language_tree_view.append_column(column_text)

        self.component.zim_language_tree_view.get_selection().set_mode(Gtk.SelectionMode(3))
        self.component.zim_language_tree_view.set_model(self.component.zim_language_list_store)
        self.component.zim_language_tree_view.get_selection().select_all()
        self.component.zim_language_tree_view.get_selection().connect("changed", self.zim_language_selection_changed)

        self.refresh_disk_list()

        self.reset_config()  # will calculate free space

        self.component.window.show()

    def reset_config(self):
        ''' restore UI to its initial (non-configured) state '''

        # name
        self.component.project_name_entry.set_text("Kiwix Plug")

        # language
        index = -1
        for i, (code, language) in enumerate(data.ideascube_languages):
            if code == 'en':
                index = i
        self.component.language_combobox.set_active(index)

        # timezone
        default_id = -1
        local_tz = tzlocal.get_localzone()
        for id, timezone in enumerate(pytz.common_timezones):
            if timezone == "UTC" and default_id == -1:
                default_id = id
            if pytz.timezone(timezone) == local_tz:
                default_id = id
            self.component.timezone_tree_store.append(None, [timezone])
        self.component.timezone_combobox.set_active(default_id)

        # wifi
        self.component.wifi_password_switch.set_active(True)
        self.component.wifi_password_entry.set_text("kiwixplug-wifipwd")

        # admin account
        self.component.admin_account_switch.set_active(False)
        self.component.admin_account_login_entry.set_text("admin")
        self.component.admin_account_pwd_entry.set_text("admin-password")

        # branding
        for key in ('logo', 'favicon', 'css'):
            getattr(self.component, '{}_chooser'.format(key)).unselect_all()

        # build_dir
        self.component.build_path_chooser.unselect_all()

        # size
        self.component.size_entry.set_text('')

        # content
        for key in ('kalite', 'wikifundi'):
            for lang, button in getattr(self, 'iter_{}_check_button'
                                              .format(key))():
                button.set_active(False)

        for key in ('edupi', 'aflatoun'):
            getattr(self.component, '{}_switch'.format(key)).set_active(False)

        # edupi resources
        self.component.edupi_resources_url_entry.set_text('')
        self.component.edupi_resources_chooser.unselect_all()

        # static contents
        for index, zim in enumerate(self.component.zim_list_store):
            if zim[8]:
                self.component.zim_list_store[index][8] = False
        self.component.choosen_zim_tree_view.set_model(self.component.zim_list_store)
        choosen_zim_filter = self.component.zim_list_store.filter_new()
        choosen_zim_filter.set_visible_func(self.choosen_zim_filter_func)
        self.component.choosen_zim_tree_view.set_model(choosen_zim_filter)

        self.update_free_space()


    def iter_kalite_check_button(self):
        return [("fr", self.component.kalite_fr_check_button),
                ("en", self.component.kalite_en_check_button),
                ("es", self.component.kalite_es_check_button)]

    def iter_wikifundi_check_button(self):
        return [("fr", self.component.wikifundi_fr_check_button),
                ("en", self.component.wikifundi_en_check_button)]

    def space_error_window_ok_button_clicked(self, widget):
        self.component.space_error_window.hide()

    def activate_menu_about(self, widget):
        response = self.component.about_dialog.run()
        if response == Gtk.ResponseType.DELETE_EVENT or response == Gtk.ResponseType.CANCEL:
            self.component.about_dialog.hide()

    def activate_menu_help(self, widget):
        webbrowser.open(data.help_url)

    def installation_done(self, error):
        ok = error == None
        validate_label(self.component.done_label, ok)
        if ok:
            self.component.done_label.set_text("Installation done")
        else:
            self.component.done_label.set_text("Installation failed")

        self.component.done_window.show()
        self.component.run_install_running_buttons_revealer.set_reveal_child(False)
        self.component.run_install_done_buttons_revealer.set_reveal_child(True)

    def run_text_view_scroll_down(self, widget):
        text_buffer = self.component.run_text_view.get_buffer()
        text_buffer.set_modified(False)

        end = text_buffer.get_end_iter()
        end.backward_line()

        self.component.run_text_view.scroll_to_iter(end, 0, True, 0, 1.)

    def run_window_delete_event(self, widget, path):
        return True

    def cancel_run(self):
        self.cancel_event.cancel()
        quit()

    def run_quit_button_clicked(self, widget):
        self.cancel_run()

    def run_abort_button_clicked(self, widget):
        dialog = ShortDialog(self.component.run_window, (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK), "Are you sure you want to abort the installation ?\nyou will not be able to resume.")
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            self.cancel_run()

        dialog.destroy()

    def run_new_install_button_clicked(self, widget):
        self.component.run_window.hide()
        self.component.window.show()

    def display_error_message(self, title, message=None,
                              parent=None, flags=None):
        if parent is None:
            parent = self.component.window
        dialog = Gtk.MessageDialog(
            parent, flags, Gtk.MessageType.ERROR,
            Gtk.ButtonsType.OK, title)
        if message is not None:
            dialog.format_secondary_text(message)
        dialog.set_modal(True)
        dialog.run()
        dialog.destroy()

    def activate_menu_config(self, widget, for_save=False):
        def _save(dialog):
            filename = dialog.get_filename() \
                if dialog.get_filename().endswith('.json') \
                else "{}.json".format(dialog.get_filename())
            try:
                with open(filename, 'w') as fd:
                    json.dump(self.get_config(), fd, indent=4)
            except Exception:
                self.display_error_message(
                    "Unable to save JSON configuration to file",
                    "Please check that the path is reachable and writable.")

        def _load(dialog):
            try:
                with open(dialog.get_filename(), 'r') as fd:
                    config = json.load(fd)
            except Exception:
                self.display_error_message(
                    "Unable to load JSON configuration",
                    "Please check that the file is readable "
                    "and in proper JSON format")
            else:
                self.set_config(config)

        if for_save:
            title = "Select a file to save Kiwix-plug config to"
            action = Gtk.FileChooserAction.SAVE
            on_accept = _save
        else:
            title = "Select Kiwix-plug config file to load"
            action = Gtk.FileChooserAction.OPEN
            on_accept = _load

        if hasattr(Gtk, 'FileChooserNative'):
            dialog = Gtk.FileChooserNative.new(
                title,
                self.component.window,  # make it tied to parent and modal
                action, "OK", "Cancel")
        else:
            dialog = Gtk.FileChooserDialog(
                title, self.component.window,
                action=action,
                buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                         Gtk.STOCK_OK, Gtk.ResponseType.ACCEPT))
        dialog.set_modal(True)  # does not seem to have effect

        filter_json = Gtk.FileFilter()
        filter_json.set_name("JSON files")
        filter_json.add_mime_type("application/json")
        filter_json.add_pattern("*.json")
        dialog.add_filter(filter_json)

        response = dialog.run()

        if response == Gtk.ResponseType.ACCEPT:
            on_accept(dialog)
        dialog.destroy()

    def set_config(self, config):
        if not isinstance(config, dict):
            return

        # reset all options
        self.reset_config()

        # project_name
        if "project_name" in config:
            self.component.project_name_entry.set_text(
                config.get("project_name"))

        # language
        try:
            value = dict(data.ideascube_languages)[config['language']]
            item_tuple = (config['language'], value)
            item_id = data.ideascube_languages.index(item_tuple)
        except KeyError:
            pass
        else:
            self.component.language_combobox.set_active(item_id)

        # timezone
        try:
            item_id = [row_id for row_id, row_data
                       in enumerate(self.component.timezone_tree_store)
                       if row_data[0] == config['timezone']][0]
        except (KeyError, IndexError):
            pass
        else:
            self.component.timezone_combobox.set_active(item_id)

        # wifi
        if "wifi" in config and isinstance(config["wifi"], dict):
            if "protected" in config["wifi"]:
                self.component.wifi_password_switch.set_active(
                    not bool(config["wifi"]["protected"]))
            if "password" in config["wifi"]:
                self.component.wifi_password_entry.set_text(
                    config["wifi"]["password"])

        # admin account
        if "admin_account" in config \
                and isinstance(config["admin_account"], dict):
            if config["admin_account"].get("custom") is not None:
                self.component.admin_account_switch.set_active(
                    bool(config["admin_account"]["custom"]))

            for key, arg_key in {'login': 'login', 'password': 'pwd'}.items():
                if config["admin_account"].get(key) is not None:
                    getattr(self.component, 'admin_account_{}_entry'
                            .format(arg_key)) \
                        .set_text(config["admin_account"][key])

        # branding
        if "branding" in config and isinstance(config["branding"], dict):
            folder = tempfile.mkdtemp()
            for key in ('logo', 'favicon', 'css'):
                if config["branding"].get(key) is not None:
                    try:
                        fpath = b64decode(
                            fname=config["branding"][key]['fname'],
                            data=config["branding"][key]['data'], to=folder)
                    except Exception:
                        pass
                    else:
                        getattr(self.component, '{}_chooser'.format(key)) \
                            .set_filename(fpath)

        # build_dir
        if config.get("build_dir") is not None:
            self.component.build_path_chooser.set_filename(
                os.path.abspath(config["build_dir"]))

        # size
        if config.get("size") is not None:
            try:
                size = humanfriendly.parse_size(config["size"]) \
                    if isinstance(config['size'], str) else config['size']
                size = int(size / ONE_GB)
            except Exception:
                size = None
            if size is not None:
                self.component.size_entry.set_text(str(size))

        # content
        if "content" in config and isinstance(config["content"], dict):

            # langs-related contents
            for key in ('kalite', 'wikifundi'):
                if key in config["content"] \
                        and isinstance(config["content"][key], list):
                    for lang, button in getattr(
                            self, 'iter_{}_check_button'.format(key))():
                        button.set_active(lang in config["content"][key])

            # boolean contents (switches)
            for key in ('edupi', 'aflatoun'):
                if config["content"].get(key) is not None:
                    getattr(self.component, '{}_switch'.format(key)) \
                        .set_active(config["content"][key])

            # edupi resources
            if config["content"].get("edupi_resources") is not None:
                rsc = config["content"].get("edupi_resources")
                if isremote(rsc):
                    self.component.edupi_resources_url_entry \
                        .set_text(str(rsc))
                else:
                    self.component.edupi_resources_chooser \
                        .set_filename(str(rsc))

            if "zims" in config["content"] \
                    and isinstance(config["content"]["zims"], list):

                nb_zims = len(self.component.zim_tree_view.get_model())
                index = 0
                nb_selected = 0
                while index < (nb_zims - nb_selected):
                    try:
                        zim = self.component.zim_tree_view.get_model()[index]
                    except IndexError:
                        break
                    selected = zim[0] in config["content"]["zims"]

                    self.component.zim_tree_view.get_model()[index][8] = \
                        selected

                    if selected:
                        nb_selected += 1
                    else:
                        index += 1
                    continue

                self.update_free_space()

    def get_config(self):
        try:
            language_id = self.component.language_combobox.get_active()
            language = data.ideascube_languages[language_id][0]
        except Exception:
            language = None

        try:
            timezone_id = self.component.timezone_combobox.get_active()
            timezone = self.component.timezone_tree_store[timezone_id][0]
        except Exception:
            timezone = None

        edupi_resources = self.get_edupi_resources()
        if edupi_resources is not None:
            if not isremote(edupi_resources):
                edupi_resources = relpathto(self.get_edupi_resources())

        zim_install = []
        for zim in self.component.zim_list_store:
            if zim[8]:
                zim_install.append(zim[0])

        kalite_active_langs = [
            lang for lang, button in self.iter_kalite_check_button()
            if button.get_active()]

        wikifundi_active_langs = [
            lang for lang, button in self.iter_wikifundi_check_button()
            if button.get_active()]

        try:
            size = int(self.component.size_entry.get_text()) * ONE_GB
        except Exception:
            size = None

        branding = {}
        for key in ('logo', 'favicon', 'css'):
            fpath = getattr(self.component,
                            '{}_chooser'.format(key)).get_filename()
            if fpath is not None and os.path.exists(fpath):
                try:
                    branding[key] = {'fname': os.path.basename(fpath),
                                     'data': b64encode(fpath)}
                except Exception:
                    pass

        return OrderedDict([
            ("project_name", self.component.project_name_entry.get_text()),
            ("language", language),
            ("timezone", timezone),
            ("wifi", {
                "protected":
                    not self.component.wifi_password_switch.get_active(),
                "password": self.component.wifi_password_entry.get_text(),
            }),
            ("admin_account", {
                "custom": self.component.admin_account_switch.get_active(),
                "login": self.component.admin_account_login_entry.get_text(),
                "password": self.component.admin_account_pwd_entry.get_text(),
            }),
            ("build_dir",
                relpathto(self.component.build_path_chooser.get_filename())),
            ("size", None if size is None else human_readable_size(size, False)),
            ("content", {
                "zims": zim_install,  # content-ids list
                "kalite": kalite_active_langs,  # languages list
                "wikifundi": wikifundi_active_langs,  # languages list
                "aflatoun": self.component.aflatoun_switch.get_active(),
                "edupi": self.component.edupi_switch.get_active(),
                "edupi_resources": edupi_resources,
            }),
            ("branding", branding),
        ])

    def reset_run_window(self):
        self.component.run_install_done_buttons_revealer.set_reveal_child(False)
        self.component.run_install_running_buttons_revealer.set_reveal_child(True)
        self.component.run_text_view.get_buffer().set_text("")
        self.logger.update()

    def run_copy_log_to_clipboard_button_clicked(self, widget):
        text_buffer = self.component.run_text_view.get_buffer()
        start = text_buffer.get_start_iter()
        end = text_buffer.get_end_iter()
        hidden = True
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text_buffer.get_text(start, end, hidden), -1)

    def run_installation_button_clicked(self, button):
        all_valid = True

        project_name = self.component.project_name_entry.get_text()
        allowed_chars = set(string.ascii_uppercase + string.ascii_lowercase + string.digits + '-' + ' ')
        condition = len(project_name) >= 1 and len(project_name) <= 64 and set(project_name) <= allowed_chars
        validate_label(self.component.project_name_label, condition)
        self.component.project_name_constraints_revealer.set_reveal_child(not condition)
        all_valid = all_valid and condition

        language_id = self.component.language_combobox.get_active()
        language = data.ideascube_languages[language_id][0]
        condition = language_id != -1
        validate_label(self.component.language_label, condition)
        all_valid = all_valid and condition

        timezone_id = self.component.timezone_combobox.get_active()
        timezone = self.component.timezone_tree_store[timezone_id][0]
        condition = timezone_id != -1
        validate_label(self.component.timezone_label, condition)
        all_valid = all_valid and condition

        if self.component.wifi_password_switch.get_state():
            wifi_pwd = None
            condition = True
        else:
            wifi_pwd = self.component.wifi_password_entry.get_text()
            condition = len(wifi_pwd) <= 31 and set(wifi_pwd) <= set(string.ascii_uppercase + string.ascii_lowercase + string.digits)
        self.component.wifi_password_constraints_revealer.set_reveal_child(not condition)
        validate_label(self.component.wifi_password_label, condition)
        all_valid = all_valid and condition

        if not self.component.admin_account_switch.get_state():
            admin_account = None
            login_condition = True
            pwd_condition = True
        else:
            admin_account = {
                "login": self.component.admin_account_login_entry.get_text(),
                "pwd": self.component.admin_account_pwd_entry.get_text(),
            }
            login_condition = len(admin_account["login"]) <= 31 and set(admin_account["login"]) <= set(string.ascii_uppercase + string.ascii_lowercase + string.digits + '-' + '_')
            pwd_condition = len(admin_account["pwd"]) <= 31 and set(admin_account["pwd"]) <= set(string.ascii_uppercase + string.ascii_lowercase + string.digits + '-' + '_') and (admin_account["pwd"] != admin_account["login"])
        self.component.admin_account_login_constraints_revealer.set_reveal_child(not login_condition)
        self.component.admin_account_pwd_constraints_revealer.set_reveal_child(not pwd_condition)
        validate_label(self.component.admin_account_login_label, login_condition)
        validate_label(self.component.admin_account_pwd_label, pwd_condition)
        all_valid = all_valid and pwd_condition and login_condition

        zim_install = []
        for zim in self.component.zim_list_store:
            if zim[8]:
                zim_install.append(zim[0])

        output_size = self.get_output_size()
        if self.component.output_stack.get_visible_child_name() == "sd_card":
            sd_card_id = self.component.sd_card_combobox.get_active()
            condition = sd_card_id != -1
            validate_label(self.component.sd_card_label, condition)
            all_valid = all_valid and condition

            if sd_card_id == -1:
                sd_card = None
            else:
                device_index = sd_card_info.get_device_index()
                sd_card = self.component.sd_card_list_store[sd_card_id][device_index]
        else:
            sd_card = None
            condition = output_size > 0
            validate_label(self.component.size_label, condition)
            all_valid = all_valid and condition

        condition = self.update_free_space() >= 0
        validate_label(self.component.free_space_name_label, condition)
        all_valid = all_valid and condition

        kalite_active_langs = [lang for lang, button in self.iter_kalite_check_button() if button.get_active()]
        if len(kalite_active_langs) != 0:
            kalite = kalite_active_langs
        else:
            kalite = None

        wikifundi_active_langs = [lang for lang, button in self.iter_wikifundi_check_button() if button.get_active()]
        if len(wikifundi_active_langs) != 0:
            wikifundi = wikifundi_active_langs
        else:
            wikifundi = None

        aflatoun = self.component.aflatoun_switch.get_active()

        edupi = self.component.edupi_switch.get_active()

        logo = self.component.logo_chooser.get_filename()
        favicon = self.component.favicon_chooser.get_filename()
        css = self.component.css_chooser.get_filename()

        build_dir = self.component.build_path_chooser.get_filename()
        condition = build_dir != None
        validate_label(self.component.build_path_chooser_label, condition)
        all_valid = all_valid and condition

        # Check if there is enough space in build_dir to build image
        if build_dir != None:
            free_space = get_free_space_in_dir(build_dir)
            remaining_space = free_space - output_size
            if remaining_space < 0:
                self.component.space_error_image_location_label.set_text(build_dir)
                self.component.space_error_total_space_required_label.set_text(human_readable_size(output_size))
                self.component.space_error_space_available_label.set_text(human_readable_size(free_space))
                self.component.space_error_space_missing_label.set_text(human_readable_size(-remaining_space))

                self.component.space_error_window.show()
                all_valid = False

        if all_valid:
            def target():
                run_installation(
                        name=project_name,
                        timezone=timezone,
                        language=language,
                        wifi_pwd=wifi_pwd,
                        kalite=kalite,
                        wikifundi=wikifundi,
                        aflatoun=aflatoun,
                        edupi=edupi,
                        edupi_resources=self.get_edupi_resources(),
                        zim_install=zim_install,
                        size=output_size,
                        logger=self.logger,
                        cancel_event=self.cancel_event,
                        sd_card=sd_card,
                        logo=logo,
                        favicon=favicon,
                        css=css,
                        build_dir=build_dir,
                        admin_account=admin_account,
                        done_callback=lambda error: GLib.idle_add(self.installation_done, error))

            self.component.window.hide()
            self.reset_run_window()
            self.component.run_window.show()
            threading.Thread(target=target, daemon=True).start()

    def sd_card_refresh_button_clicked(self, button):
        self.refresh_disk_list()
        self.update_free_space()

    def refresh_disk_list(self):
        active_id = self.component.sd_card_combobox.get_active()
        if active_id != -1:
            selected_device = self.component.sd_card_list_store[active_id]
            selected_device = selected_device[sd_card_info.get_device_index()]
        else:
            selected_device = None

        self.component.sd_card_list_store.clear()

        for id, device in enumerate(sd_card_info.get_iterator()):
            items = [info["typ"](device[info["name"]]) for info in sd_card_info.informations]
            self.component.sd_card_list_store.append(items)
            device_name = str(device['device']).rstrip('\0')
            if device_name == selected_device:
                self.component.sd_card_combobox.set_active(id)

    def zim_choose_content_button_clicked(self, button):
        self.component.zim_window.show()

    def get_edupi_resources(self):
        local_rsc = self.component.edupi_resources_chooser.get_filename()
        remote_rsc = self.component.edupi_resources_url_entry.get_text()
        return (remote_rsc if remote_rsc else local_rsc) or None

    def get_free_space(self):
        zim_list = []
        for zim in self.component.zim_list_store:
            if zim[8]:
                zim_list.append(zim[0])

        kalite = []
        for lang, button in self.iter_kalite_check_button():
            if button.get_active():
                kalite.append(lang)

        wikifundi = []
        for lang, button in self.iter_wikifundi_check_button():
            if button.get_active():
                wikifundi.append(lang)

        aflatoun = self.component.aflatoun_switch.get_active()
        edupi = self.component.edupi_switch.get_active()
        edupi_resources = self.get_edupi_resources()

        collection = get_collection(
            edupi=edupi,
            edupi_resources=edupi_resources,
            packages=zim_list,
            kalite_languages=kalite,
            wikifundi_languages=wikifundi,
            aflatoun_languages=['fr', 'en'] if aflatoun else [])
        required_image_size = get_required_image_size(collection)

        return self.get_output_size() - required_image_size

    def update_free_space(self):
        free_space = self.get_free_space()
        human_readable_free_space = human_readable_size(free_space)
        self.component.free_space_label1.set_text(human_readable_free_space)
        self.component.free_space_label2.set_text(human_readable_free_space)
        condition = free_space >= 0
        validate_label(self.component.free_space_label1, condition)
        validate_label(self.component.free_space_label2, condition)

        # size_entry should be at least base_image size
        size = self.get_output_size()
        validate_label(
            self.component.size_entry,
            size >= get_content('pibox_base_image')['expanded_size'])

        for row in self.component.zim_list_store:
            if free_space - int(row[9]) >= 0:
                row[11] = VALID_RGBA
            else:
                row[11] = INVALID_RGBA
        return free_space

    def get_output_size(self):
        if self.component.output_stack.get_visible_child_name() == "sd_card":
            sd_card_id = self.component.sd_card_combobox.get_active()
            if sd_card_id == -1:
                size = -1
            else:
                get_size_index = sd_card_info.get_size_index()
                size = int(self.component.sd_card_list_store[sd_card_id][get_size_index])
        else:
            try:
                size = int(self.component.size_entry.get_text()) * ONE_GB
            except:
                size = -1

        return size

    def zim_language_selection_changed(self, selection):
        model, rows = selection.get_selected_rows()

        selected_languages = set()
        for row in rows:
            selected_languages.add(model[row][0])

        for zim in self.component.zim_list_store:
            zim[10] = len(zim[5] & selected_languages) != 0

    def available_zim_clicked(self, tree_view, path, column):
        tree_view.get_model()[path][8] = True
        tree_view.get_selection().unselect_all()
        self.update_free_space()

    def choosen_zim_clicked(self, tree_view, path, column):
        tree_view.get_model()[path][8] = False
        tree_view.get_selection().unselect_all()
        self.update_free_space()

    def zim_done_button_clicked(self, widget):
        self.component.zim_window.hide()

    def zim_filter_func(self, model, iter, data):
        return model[iter][10] and not model[iter][8]

    def choosen_zim_filter_func(self, model, iter, data):
        return model[iter][8]

try:
    assert len(YAML_CATALOGS)
except Exception as exception:
    dialog = ShortDialog(None, (Gtk.STOCK_OK, Gtk.ResponseType.OK), "Catalog downloads failed, you may check your internet connection")
    dialog.run()
    print(exception, file=sys.stderr)
    dialog.destroy()
    sys.exit(1)

Application(YAML_CATALOGS)

run()
