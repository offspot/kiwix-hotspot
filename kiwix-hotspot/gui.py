# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import sys
import json
import platform
import tempfile
import threading
import multiprocessing
from collections import OrderedDict

import gi
import pytz
import iso639
import tzlocal
import requests
import humanfriendly
import webbrowser


from backend.content import (
    get_expanded_size,
    get_collection,
    get_required_image_size,
    get_content,
    isremote,
)
import data
import sd_card_info
from util import relpathto
from util import get_cache
from util import CLILogger
from util import check_user_inputs
from version import get_version_str
from util import b64encode, b64decode
from util import get_free_space_in_dir
from util import get_adjusted_image_size
from util import split_proxy, save_prefs
from backend.catalog import get_catalogs
from util import CancelEvent, ProgressHelper
from run_installation import run_installation
from backend.util import sd_has_single_partition, flash_image_with_etcher
from backend.mount import open_explorer_for_imdisk
from util import human_readable_size, ONE_GB, ONE_MiB
from backend.cache import clean_cache, reset_cache
from backend.cache import get_cache_size_and_free_space
from backend.download import get_proxies, test_connection

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, GObject

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
        Gtk.Dialog.__init__(self, "Kiwix Hotspot", parent, 0, buttons)
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

    @property
    def on_tty(self):
        return False

    def flash(self, line):
        pass

    def ascii_progressbar(self, current, total):
        width = 60
        avail_dots = width - 2
        if total == -1:
            line = "unknown size"
        elif current >= total:
            line = "[" + "." * avail_dots + "] 100%\n"
        else:
            ratio = min(float(current) / total, 1.)
            shaded_dots = min(int(ratio * avail_dots), avail_dots)
            percent = min(int(ratio * 100), 100)
            line = (
                "["
                + "." * shaded_dots
                + " " * (avail_dots - shaded_dots)
                + "] "
                + str(percent)
                + "%\r"
            )

        if getattr(self, "_last_progress_line", None) != line:
            self.raw_std(line)
            setattr(self, "_last_progress_line", line)

    def step(self, step):
        GLib.idle_add(self.main_thread_step, step)

    def err(self, err):
        GLib.idle_add(self.main_thread_err, err)

    def succ(self, succ):
        GLib.idle_add(self.main_thread_succ, succ)

    def raw_std(self, std):
        GLib.idle_add(self.main_thread_raw_std, std, end="")

    def std(self, std, end=None):
        GLib.idle_add(self.main_thread_std, std, end)

    def complete(self):
        GLib.idle_add(self.main_thread_complete)

    def failed(self, error):
        GLib.idle_add(self.main_thread_failed, error)

    def main_thread_text(self, text, end="\n", tag=None):
        if not isinstance(text, str):
            text = str(text)
        text = self._add_time(text)
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

    def main_thread_succ(self, text):
        self.main_thread_text(text, "\n", self.succ_tag)

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
        self.main_thread_text(
            "[STAGE {nums}: {name} - {pc:.0f}%]".format(
                nums=self.stage_numbers,
                name=self.stage_name,
                pc=self.get_overall_progress() * 100,
            ),
            tag=self.stg_tag,
        )

        # update overall percentage on window title
        self.component.run_window.set_title(
            "Kiwix Hotspot ({:.0f}%)".format(self.get_overall_progress() * 100)
        )

        # update stage name and number (Stage x/y)
        self.component.run_step_label.set_markup(
            "<b>Stage {nums}</b>: {name}".format(
                nums=self.stage_numbers, name=self.stage_name
            )
        )

        # update the progress bar according to the stage's progress
        if self.stage_progress is not None:
            self.component.run_progressbar.set_inverted(False)
            self.component.run_progressbar.set_fraction(self.stage_progress)
        else:
            # animate the stage progress bar to show an unknown progress
            self.run_pulse()

    def main_thread_complete(self):
        super(Logger, self).complete()
        self.main_thread_succ("Installation succeded.")
        self.component.run_step_label.set_markup("<b>Done.</b>")
        self.progress(1)

    def main_thread_failed(self, error):
        super(Logger, self).failed()
        self.step("Failed: {}".format(error[0:50]))
        self.err("Installation failed: {}".format(error))
        self.progress(1)

    def run_pulse(self):
        """ used for progress bar animation (unknown progress) """
        self._update_progress_text("")
        self.timeout_id = GObject.timeout_add(50, self.on_timeout)

    def on_timeout(self):
        """ used for progress bar animation (unknown progress) """
        if self.stage_progress is None:
            new_value = self.component.run_progressbar.get_fraction() + 0.035
            # inverse direction if end reached
            if new_value > 1:
                new_value = 0
                # switch from left-to-right to right-to-left at bounds
                self.component.run_progressbar.set_inverted(
                    not self.component.run_progressbar.get_inverted()
                )
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
    def __init__(self):
        self.catalogs = None

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
        self.component.favicon_chooser.add_filter(self.component.favicon_filter)

        self.component.logo_filter.set_name("Logo (PNG)")  # opt
        self.component.logo_filter.add_pattern("*.png")
        self.component.logo_chooser.add_filter(self.component.logo_filter)

        self.component.css_filter.set_name("CSS File")  # opt
        self.component.css_filter.add_pattern("*.css")
        self.component.css_chooser.add_filter(self.component.css_filter)

        self.component.edupi_resources_filter.set_name("ZIP File")  # opt
        self.component.edupi_resources_filter.add_pattern("*.zip")
        self.component.edupi_resources_chooser.add_filter(
            self.component.edupi_resources_filter
        )

        # menu bar
        self.component.menu_quit.connect(
            "activate", lambda widget: self.component.window.close()
        )
        self.component.menu_about.connect("activate", self.activate_menu_about)

        self.component.menu_load_config.connect(
            "activate", self.activate_menu_config, False
        )
        self.component.menu_save_config.connect(
            "activate", self.activate_menu_config, True
        )
        self.component.menu_help.connect("activate", self.activate_menu_help)

        # imdisk menu is windows only
        if sys.platform == "win32":
            self.component.menu_imdisk.set_visible(True)
            self.component.menu_imdisk.connect("activate", self.activate_menu_imdisk)

        # proxies
        self.component.menu_proxies.connect(
            "activate", lambda widget: self.component.proxies_dialog.show()
        )
        self.component.reset_proxies_button.connect(
            "clicked", self.reset_proxies_button_clicked
        )
        self.component.save_proxies_button.connect(
            "clicked", self.save_proxies_button_clicked
        )
        self.component.test_proxies_button.connect(
            "clicked", self.test_proxies_button_clicked
        )
        self.component.proxies_dialog.connect(
            "show", lambda widget: self._set_proxies_entries()
        )
        self.component.proxies_dialog.connect("delete-event", hide_on_delete)

        # etcher
        self.component.menu_etcher.connect("activate", self.activate_menu_etcher)

        # cache
        self.component.clean_cache_button.connect("clicked", self.activate_menu_cache)

        # sd clean
        self.component.clean_sd_button.connect("clicked", self.activate_sd_clean)

        # wifi password
        self.component.wifi_password_switch.connect(
            "notify::active",
            lambda switch, state: self.component.wifi_password_revealer.set_reveal_child(
                not switch.get_active()
            ),
        )

        # edupi resources
        self.component.edupi_switch.connect(
            "notify::active",
            lambda switch, state: self.component.edupi_resources_revealer.set_reveal_child(
                switch.get_active()
            ),
        )

        # ideascube language
        for code, language in data.hotspot_languages:
            self.component.language_tree_store.append([code, language])

        renderer = Gtk.CellRendererText()
        self.component.language_combobox.pack_start(renderer, True)
        self.component.language_combobox.add_attribute(renderer, "text", 1)

        # SD sizes for image size
        for ngb in data.sdcard_sizes:
            self.component.sizes_tree_store.append([str(ngb), "{} GB".format(ngb)])
        renderer = Gtk.CellRendererText()
        self.component.size_combobox.pack_start(renderer, True)
        self.component.size_combobox.add_attribute(renderer, "text", 1)

        renderer = Gtk.CellRendererText()
        self.component.timezone_combobox.pack_start(renderer, True)
        self.component.timezone_combobox.add_attribute(renderer, "text", 0)

        # build-path
        self.component.build_path_chooser.connect("file-set", self.changed_build_path)

        # output
        self.component.sd_card_combobox.connect(
            "changed", lambda _: self.update_free_space()
        )
        self.component.sd_card_combobox.connect(
            "changed", lambda w: self.on_sdcard_selection_change(w)
        )
        self.component.sd_card_refresh_button.connect(
            "clicked", self.sd_card_refresh_button_clicked
        )
        self.component.output_stack.connect(
            "notify::visible-child", lambda switch, state: self.update_free_space()
        )
        self.component.size_combobox.connect(
            "changed", lambda _: self.update_free_space()
        )

        types = [info["typ"] for info in sd_card_info.informations]
        self.component.sd_card_list_store = Gtk.ListStore(*types)
        self.component.sd_card_combobox.set_model(self.component.sd_card_list_store)

        for counter in range(0, sd_card_info.visible_informations):
            cell_renderer = Gtk.CellRendererText()
            self.component.sd_card_combobox.pack_start(cell_renderer, True)
            self.component.sd_card_combobox.add_attribute(
                cell_renderer, "text", counter
            )

        # about dialog
        self.component.about_dialog.set_logo(
            GdkPixbuf.Pixbuf.new_from_file_at_scale(data.pibox_logo, 200, -1, True)
        )
        self.component.about_dialog.set_version(get_version_str())

        # done window
        self.component.done_window_ok_button.connect(
            "clicked", lambda widget: self.component.done_window.hide()
        )
        self.component.done_window.connect("delete-event", hide_on_delete)

        # space error window
        self.component.space_error_window_ok_button.connect(
            "clicked", self.space_error_window_ok_button_clicked
        )
        self.component.space_error_window.connect("delete-event", hide_on_delete)

        # run window
        self.component.run_installation_button.connect(
            "clicked", self.run_installation_button_clicked
        )
        self.component.run_window.connect("delete-event", self.run_window_delete_event)
        self.component.run_text_view.get_buffer().connect(
            "modified-changed", self.run_text_view_scroll_down
        )
        self.component.run_quit_button.connect("clicked", self.run_quit_button_clicked)
        self.component.run_abort_button.connect(
            "clicked", self.run_abort_button_clicked
        )
        self.component.run_copy_log_to_clipboard_button.connect(
            "clicked", self.run_copy_log_to_clipboard_button_clicked
        )
        self.component.run_new_install_button.connect(
            "clicked", self.run_new_install_button_clicked
        )

        # zim content
        self.component.zim_choose_content_button.connect(
            "clicked", self.zim_choose_content_button_clicked
        )

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
            Gdk.RGBA,  # background color
        )
        self.component.zim_list_store.set_sort_column_id(1, Gtk.SortType.ASCENDING)

        def get_project_size(name, lang):
            langs = ["fr", "en"] if name == "aflatoun" else [lang]
            return get_expanded_size(
                get_collection(**{"{}_languages".format(name): langs})
            )

        # kalite
        for lang, button in self.iter_kalite_check_button():
            button.set_label(
                "{} ({})".format(
                    button.get_label(),
                    human_readable_size(get_project_size("kalite", lang)),
                )
            )
            button.connect("toggled", lambda button: self.update_free_space())

        # wikifundi
        for lang, button in self.iter_wikifundi_check_button():
            button.set_label(
                "{} ({})".format(
                    button.get_label(),
                    human_readable_size(get_project_size("wikifundi", lang)),
                )
            )
            button.connect("toggled", lambda button: self.update_free_space())

        # aflatoun
        self.component.aflatoun_switch.connect(
            "notify::active", lambda switch, state: self.update_free_space()
        )
        self.component.aflatoun_label.set_label(
            "{} ({})".format(
                self.component.aflatoun_label.get_label(),
                human_readable_size(get_project_size("aflatoun", lang)),
            )
        )

        # edupi
        self.component.edupi_switch.connect(
            "notify::active", lambda switch, state: self.update_free_space()
        )
        self.component.edupi_label.set_label(
            "{} ({})".format(
                self.component.edupi_label.get_label(),
                human_readable_size(10 * ONE_MiB),
            )
        )
        self.component.edupi_resources_url_entry.connect(
            "changed", lambda _: self.update_free_space()
        )
        self.component.edupi_resources_chooser.connect(
            "file-set", lambda _: self.update_free_space()
        )

        self.refresh_disk_list()

        self.reset_config()  # will calculate free space

        self.component.window.show()

        self.catalogs_thread = threading.Thread(target=self.download_catalogs)
        self.catalogs_thread.start()

    def ensure_connection(self):
        """ test and return Connection Status. Display Error of failure """
        conn_working, failed_protocol = test_connection()
        if not conn_working:
            self.display_error_message(
                "Internet Connection Failed ({})".format(failed_protocol),
                "Unable to contact Kiwix Server.\nPlease check your Internet Connection and/or Proxy Settings (from the File menu).",
                self.component.window,
            )
            return False
        return True

    def download_catalogs(self):
        self.catalogs = get_catalogs(CLILogger())
        return self.catalogs is not None

    def ensure_catalogs(self):
        if self.catalogs_thread.is_alive():
            # let's wait for the catalog thread to complete
            self.catalogs_thread.join()
        if self.catalogs is None:
            if not self.download_catalogs():
                self.display_error_message(
                    title="Catalogs Download Failed",
                    message="Could not download the Content Catalogs. Please check your Internet connection and/or Proxy Settings (File menu).",
                    parent=self.component.window,
                )
                return False
        # now that we have the catalogs, build the ZIM store if not already done
        if not len(self.component.zim_list_store):
            self.build_zim_store()
        return True

    def build_zim_store(self):
        all_languages = set()

        for one_catalog in self.catalogs:
            for (key, value) in one_catalog["all"].items():
                name = value["name"]
                url = value["url"]
                description = value.get("description") or "none"
                size = str(value["size"])
                languages = []
                for iso_code in (value.get("language") or "Unknown language").split(
                    ","
                ):
                    try:
                        languages.append(iso639.languages.get(part3=iso_code).name)
                    except KeyError:
                        pass
                languages = set(languages)
                typ = value["type"]
                version = str(value["version"])
                formatted_size = human_readable_size(int(size))

                self.component.zim_list_store.append(
                    [
                        key,
                        name,
                        url,
                        description,
                        formatted_size,
                        languages,
                        typ,
                        version,
                        False,
                        size,
                        True,
                        VALID_RGBA,
                    ]
                )
                all_languages |= languages

        self.component.zim_language_list_store = Gtk.ListStore(str)
        self.component.zim_language_list_store.set_sort_column_id(
            0, Gtk.SortType.ASCENDING
        )
        for language in all_languages:
            self.component.zim_language_list_store.append([language])

        # zim window
        self.component.zim_window_done_button.connect(
            "clicked", self.zim_done_button_clicked
        )
        self.component.zim_window.connect("delete-event", hide_on_delete)
        self.component.zim_tree_view.connect(
            "row-activated", self.available_zim_clicked
        )
        self.component.choosen_zim_tree_view.connect(
            "row-activated", self.choosen_zim_clicked
        )

        # zim window available tree view
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

        # language tree view
        renderer_text = Gtk.CellRendererText()
        column_text = Gtk.TreeViewColumn("Language", renderer_text, text=0)
        self.component.zim_language_tree_view.append_column(column_text)

        self.component.zim_language_tree_view.get_selection().set_mode(
            Gtk.SelectionMode(3)
        )
        self.component.zim_language_tree_view.set_model(
            self.component.zim_language_list_store
        )
        self.component.zim_language_tree_view.get_selection().select_all()
        self.component.zim_language_tree_view.get_selection().connect(
            "changed", self.zim_language_selection_changed
        )

        # apply chosen zim filter
        choosen_zim_filter = self.component.zim_list_store.filter_new()
        choosen_zim_filter.set_visible_func(self.choosen_zim_filter_func)
        self.component.choosen_zim_tree_view.set_model(choosen_zim_filter)

        self.update_free_space()

    def reset_config(self):
        """ restore UI to its initial (non-configured) state """

        # name
        self.component.project_name_entry.set_text("Kiwix")

        # language
        index = -1
        for i, (code, language) in enumerate(data.hotspot_languages):
            if code == "en":
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
        self.component.wifi_password_entry.set_text("hotspot-password")

        # admin account
        self.component.admin_account_login_entry.set_text("admin")
        self.component.admin_account_pwd_entry.set_text("admin-password")

        # branding
        for key in ("logo", "favicon", "css"):
            getattr(self.component, "{}_chooser".format(key)).unselect_all()

        # build_dir
        self.component.build_path_chooser.unselect_all()

        # size
        self.component.size_combobox.set_active(0)

        # content
        for key in ("kalite", "wikifundi"):
            for lang, button in getattr(self, "iter_{}_check_button".format(key))():
                button.set_active(False)

        for key in ("edupi", "aflatoun"):
            getattr(self.component, "{}_switch".format(key)).set_active(False)

        # edupi resources
        self.component.edupi_resources_url_entry.set_text("")
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
        return [
            ("fr", self.component.kalite_fr_check_button),
            ("en", self.component.kalite_en_check_button),
            ("es", self.component.kalite_es_check_button),
        ]

    def iter_wikifundi_check_button(self):
        return [
            ("fr", self.component.wikifundi_fr_check_button),
            ("en", self.component.wikifundi_en_check_button),
        ]

    def space_error_window_ok_button_clicked(self, widget):
        self.component.space_error_window.hide()

    def activate_menu_about(self, widget):
        response = self.component.about_dialog.run()
        if (
            response == Gtk.ResponseType.DELETE_EVENT
            or response == Gtk.ResponseType.CANCEL
        ):
            self.component.about_dialog.hide()

    def activate_menu_help(self, widget):
        webbrowser.open(data.help_url)

    def _set_proxies_entries(self, proxies=None):
        """ fill proxies_dialog entries with proxies conf (passed or prefs) """
        proxies = proxies if proxies is not None else get_proxies()
        http_loc, http_port = split_proxy(proxies.get("http", ""))
        self.component.http_proxy_entry.set_text(http_loc)
        self.component.http_proxy_port_entry.set_text(http_port)

        https_loc, https_port = split_proxy(proxies.get("https", ""))
        self.component.https_proxy_entry.set_text(https_loc)
        self.component.https_proxy_port_entry.set_text(https_port)

    def _get_proxies_entries(self):
        """ return proxies conf from the proxies_dialog entries """
        http_proxy = self.component.http_proxy_entry.get_text().strip()
        http_proxy_port = self.component.http_proxy_port_entry.get_text().strip()
        https_proxy = self.component.https_proxy_entry.get_text().strip()
        https_proxy_port = self.component.https_proxy_port_entry.get_text().strip()

        proxies = {}
        if http_proxy and http_proxy_port:
            proxies.update(
                {
                    "http": "http://{netloc}:{port}".format(
                        netloc=http_proxy, port=http_proxy_port
                    )
                }
            )
        if https_proxy and https_proxy_port:
            proxies.update(
                {
                    "https": "http://{netloc}:{port}".format(
                        netloc=https_proxy, port=https_proxy_port
                    )
                }
            )
        return proxies

    def test_proxies_button_clicked(self, widget):
        """ test connection using the (non-saved) proxy conf in the proxies dialog """
        proxies = self._get_proxies_entries()
        conn_working, failed_protocol = test_connection(proxies=proxies)
        if conn_working:
            mtype = Gtk.MessageType.INFO
            title = "Connection Successful"
            message = (
                "We could reach Kiwix server using those settings.\n"
                "You can now save them and pursue."
            )
        else:
            mtype = Gtk.MessageType.ERROR
            title = "Connection Failed ({})".format(failed_protocol)
            message = (
                "Unable to contact Kiwix server using those Settings.\n"
                "Either your Internet Connection is not working or those settings are incorrect."
            )

        msg_box = Gtk.MessageDialog(
            self.component.proxies_dialog, None, mtype, Gtk.ButtonsType.OK, title
        )
        msg_box.format_secondary_text(message)
        msg_box.set_modal(True)
        msg_box.run()
        msg_box.destroy()

    def reset_proxies_button_clicked(self, widget):
        """ set proxies conf and prefs to not use proxy at all """

        # reset UI
        self._set_proxies_entries({})

        # save prefs and reload proxies
        save_prefs({}, auto_reload=True)
        get_proxies(load_env=False, force_reload=True)

        # close dialog
        self.component.proxies_dialog.hide()

    def save_proxies_button_clicked(self, widget):
        """ save in prefs and use proxies conf from proxies_dialog """

        proxies = self._get_proxies_entries()
        prefs = {}

        if proxies.get("http"):
            prefs.update({"HTTP_PROXY": proxies.get("http")})

        if proxies.get("https"):
            prefs.update({"HTTPS_PROXY": proxies.get("https")})

        # save prefs and reload proxies
        save_prefs(prefs, auto_reload=True)
        get_proxies(load_env=False, force_reload=True)

        # reflect changes on UI
        self._set_proxies_entries()

        # close dialog
        self.component.proxies_dialog.hide()

    def activate_menu_imdisk(self, widget):
        class ImDiskDialog(Gtk.Dialog):
            def __init__(self, parent):
                Gtk.Dialog.__init__(
                    self,
                    "Install or Uninstall ImDisk Manually",
                    parent,
                    0,
                    (
                        Gtk.STOCK_CANCEL,
                        Gtk.ResponseType.CANCEL,
                        Gtk.STOCK_OK,
                        Gtk.ResponseType.OK,
                    ),
                )

                self.set_default_size(500, 300)

                label = Gtk.Label()
                label.set_markup(
                    "\nBy selecting OK bellow, you will be directed to the "
                    "ImDisk installation folder.\n"
                    "<b>Right-click on <i>install.cmd</i></b> and choose to "
                    "<u>Run as Administrator</u>.\n"
                )
                label.set_alignment(0, 0.5)
                label2 = Gtk.Label()
                label2.set_markup(
                    "\nYou can also uninstall it from that folder by "
                    "doing the same with <i>uninstall_imdisk.cmd</i>.\n"
                )
                label2.set_alignment(0, 0.5)
                image = Gtk.Image.new_from_file(
                    os.path.join(data.data_dir, "imdisk.png")
                )
                box = self.get_content_area()
                box.add(label)
                box.add(image)
                box.add(label2)
                self.show_all()

        dialog = ImDiskDialog(self.component.window)
        if dialog.run() == Gtk.ResponseType.OK:
            open_explorer_for_imdisk(self.logger)
        dialog.close()

    def activate_menu_etcher(self, widget):
        class EtcherDialog(Gtk.Dialog):
            DL_CODE = 2111

            def __init__(self, parent):
                Gtk.Dialog.__init__(
                    self,
                    "Use Etcher to Flash your SD-card",
                    parent,
                    0,
                    (
                        "Download Latest Etcher",
                        self.DL_CODE,
                        "Visit Website",
                        Gtk.ResponseType.OK,
                        Gtk.STOCK_OK,
                        Gtk.ResponseType.CANCEL,
                    ),
                )

                self.set_default_size(500, 300)

                label = Gtk.Label()
                label.set_markup(
                    "\nUse <b>Etcher</b> to flash your image onto your SD-card"
                    ". It will also <b>validate</b> that the SD-card "
                    "has been <b>successfuly written</b>.\n"
                    "You can even burn the same image "
                    "on <b>several SD-cards at once</b>.\n"
                )
                label.set_alignment(0, 0.5)
                label2 = Gtk.Label()
                label2.set_markup(
                    "\nPlease Download and Run <b>Etcher</b> separately.\n"
                )
                label2.set_alignment(0, 0.5)
                image = Gtk.Image.new_from_file(
                    os.path.join(data.data_dir, "etcher.gif")
                )
                box = self.get_content_area()
                box.add(label)
                box.add(image)
                box.add(label2)
                self.show_all()

        dialog = EtcherDialog(self.component.window)
        ret = dialog.run()
        if ret == EtcherDialog.DL_CODE:
            try:
                req = requests.get(
                    "https://img.shields.io/github/release" "/resin-io/etcher.json"
                )
                version = req.json().get("value")
                base_url = (
                    "https://github.com/resin-io/etcher/releases/"
                    "download/{}/".format(version)
                )

                def get_fname():
                    if sys.platform == "linux":
                        if platform.machine() == "x86_64":
                            return "etcher-electron-{v}-x86_64.AppImage"
                        return "etcher-electron-{v}-i386.AppImage"
                    elif sys.platform == "win32":
                        if platform.machine() == "AMD64":
                            return "Etcher-Portable-{v}-x64.exe"
                        return "Etcher-Portable-{v}-x86.exe"
                    elif sys.platform == "darwin":
                        return "Etcher-{v}.dmg"
                    raise NotImplementedError("platform not supported")

                etcher_dl_url = base_url + get_fname().format(v=version[1:])
            except Exception as exp:
                etcher_dl_url = data.etcher_url
            webbrowser.open(etcher_dl_url)
        elif ret == Gtk.ResponseType.OK:
            webbrowser.open(data.etcher_url)
        dialog.close()

    def changed_build_path(self, widget):
        """ display Clean cache button only if build-path is set """
        self.component.clean_cache_button.set_visible(
            bool(self.component.build_path_chooser.get_filename().strip())
        )

    def activate_menu_cache(self, widget):
        build_folder = self.component.build_path_chooser.get_filename()
        cache_folder = get_cache(build_folder)
        cache_size, nb_files, free_space = get_cache_size_and_free_space(
            build_folder, cache_folder
        )

        class CacheDialog(Gtk.Dialog):
            WIPE_CODE = 2111

            def __init__(self, parent):
                Gtk.Dialog.__init__(
                    self,
                    "Reclaim space by cleaning-up your cache",
                    parent,
                    0,
                    (
                        "Wipe Cache (quick)",
                        self.WIPE_CODE,
                        "Clean Cache (slow)",
                        Gtk.ResponseType.OK,
                        "Close",
                        Gtk.ResponseType.CANCEL,
                    ),
                )

                self.parent = parent
                self.set_default_size(300, 100)

                label = Gtk.Label()
                label.set_markup(
                    "\nKiwix Hotspot maintains <b>a cache of all downloaded files</b> "
                    "and reuse them on future runs.\n"
                    "\nYou can either <b>wipe the cache completely</b> "
                    "or <b>only remove obsolete files</b>.\n"
                    "Obsoletes files are previous version of ZIMs or content packs.\n\n"
                    "Wiping is almost instantaneous.\n"
                    "Cleaning takes several minutes as "
                    "it analyzes files to determine which ones should be kept.\n\n"
                    "Your cache folder is: <i>{cache}</i>.\n"
                    "<u>Cache Disk Usage</u>: <b>{du}</b> ({nb} files)\n"
                    "<u>Free Space</u>: <b>{df}</b>\n".format(
                        cache=cache_folder,
                        du=human_readable_size(cache_size),
                        df=human_readable_size(free_space),
                        nb=nb_files,
                    )
                )
                label.set_alignment(0, 0.5)

                self.thread = None
                self.run_progressbar = Gtk.ProgressBar()
                self.cancel_button = Gtk.Button("Cancel")
                self.cancel_button.connect("clicked", self.stop_cache_operation)

                box = self.get_content_area()
                box.add(label)
                box.add(self.run_progressbar)
                box.add(self.cancel_button)
                box.add(Gtk.Label(""))  # spacer
                self.show_all()
                self.run_progressbar.set_visible(False)
                self.cancel_button.set_visible(False)

            def start_cache_operation(self, is_wipe):
                # do nothing if the thread is running
                if self.thread is not None and self.thread.is_alive():
                    return

                # show progress bar and cancel button
                self.run_progressbar.set_visible(True)
                self.cancel_button.set_label(
                    "Cancel {}".format("Wiping" if is_wipe else "Cleaning...")
                )
                self.cancel_button.set_visible(True)

                # start progress bar animation
                self.timeout_id = GObject.timeout_add(50, self.on_timeout)

                self.thread = multiprocessing.Process(
                    target=reset_cache if is_wipe else clean_cache,
                    args=(CLILogger(), build_folder, cache_folder),
                )
                self.thread.start()

            def on_timeout(self):
                # display post-thread dialog on cancelled thread
                if self.thread is not None and not self.thread.is_alive():
                    self.display_post_cache_operation_dialog()
                    return False
                elif self.thread is None:  # stop progress anim if thread not running
                    return False

                new_value = self.run_progressbar.get_fraction() + 0.035
                # inverse direction if end reached
                if new_value > 1:
                    new_value = 0
                    # switch from left-to-right to right-to-left at bounds
                    self.run_progressbar.set_inverted(
                        not self.run_progressbar.get_inverted()
                    )
                self.run_progressbar.set_fraction(new_value)
                return True  # returns True so it continues to get called

            def stop_cache_operation(self, *args, **kwargs):
                if self.thread is not None and self.thread.is_alive():
                    self.thread.terminate()
                    self.thread = None
                    self.cancel_button.set_visible(False)
                    self.run_progressbar.set_visible(False)
                self.close()

            def display_post_cache_operation_dialog(self):
                msg_box = Gtk.MessageDialog(
                    self.parent,
                    None,
                    Gtk.MessageType.INFO,
                    Gtk.ButtonsType.OK,
                    "Cache Operation Completed",
                )
                cache_size, nb_files, free_space = get_cache_size_and_free_space(
                    build_folder, cache_folder
                )
                content = (
                    "Cache folder: {cache}.\n"
                    "Cache Disk Usage: {du} ({nb} files)\n"
                    "Free Space: {df}\n\n".format(
                        cache=cache_folder,
                        du=human_readable_size(cache_size),
                        df=human_readable_size(free_space),
                        nb=nb_files,
                    )
                )
                msg_box.format_secondary_text(content)
                msg_box.set_modal(True)
                msg_box.run()
                msg_box.destroy()
                self.close()

        dialog = CacheDialog(self.component.window)
        ret = dialog.run()
        if ret == CacheDialog.WIPE_CODE:
            dialog.start_cache_operation(True)
        elif ret == Gtk.ResponseType.OK:
            dialog.start_cache_operation(False)
        else:
            dialog.close()

    def activate_sd_clean(self, widget):
        sd_card = self.get_sd_card()

        class SDCleanDialog(Gtk.Dialog):
            def __init__(self, parent, parent_ui):
                Gtk.Dialog.__init__(
                    self,
                    "Wipe your SD-card clean before for installation",
                    parent,
                    0,
                    (
                        "Wipe {}".format(sd_card),
                        Gtk.ResponseType.OK,
                        "Close",
                        Gtk.ResponseType.CANCEL,
                    ),
                )

                self.parent = parent
                self.parent_ui = parent_ui
                self.set_default_size(300, 100)

                label = Gtk.Label()
                label.set_markup(
                    "\nFor Kiwix Hotspot to work properly,\n"
                    "you need your SD-card to be cleaned before starting,\n"
                    "hence having just a single FAT-like partition.\n\n"
                    "This process you only take a few minutes.\n"
                    "If this does not end within 10mn,\n"
                    "cancel-it and try clean your SD-card using a different tool.\n\n"
                )
                label.set_alignment(0, 0.5)

                self.thread = None
                self.retcode = multiprocessing.Value("i", -1)
                self.run_progressbar = Gtk.ProgressBar()
                self.cancel_button = Gtk.Button("Cancel")
                self.cancel_button.connect("clicked", self.stop_clean_operation)

                box = self.get_content_area()
                box.add(label)
                box.add(self.run_progressbar)
                box.add(self.cancel_button)
                box.add(Gtk.Label(""))  # spacer
                self.show_all()
                self.run_progressbar.set_visible(False)
                self.cancel_button.set_visible(False)

            def start_clean_operation(self):
                # do nothing if the thread is running
                if self.thread is not None and self.thread.is_alive():
                    return

                # show progress bar and cancel button
                self.run_progressbar.set_visible(True)
                self.cancel_button.set_label("Cancel Wiping")
                self.cancel_button.set_visible(True)

                # start progress bar animation
                self.timeout_id = GObject.timeout_add(50, self.on_timeout)

                self.thread = multiprocessing.Process(
                    target=flash_image_with_etcher,
                    args=(
                        os.path.join(data.data_dir, "mbr.img"),
                        sd_card,
                        self.retcode,
                    ),
                )
                self.thread.start()

            def on_timeout(self):
                # display post-thread dialog on cancelled thread
                if self.thread is not None and not self.thread.is_alive():
                    self.display_post_clean_operation_dialog()
                    return False
                elif self.thread is None:  # stop progress anim if thread not running
                    return False

                new_value = self.run_progressbar.get_fraction() + 0.035
                # inverse direction if end reached
                if new_value > 1:
                    new_value = 0
                    # switch from left-to-right to right-to-left at bounds
                    self.run_progressbar.set_inverted(
                        not self.run_progressbar.get_inverted()
                    )
                self.run_progressbar.set_fraction(new_value)
                return True  # returns True so it continues to get called

            def stop_clean_operation(self, *args, **kwargs):
                if self.thread is not None and self.thread.is_alive():
                    self.thread.terminate()
                    self.thread = None
                    self.cancel_button.set_visible(False)
                    self.run_progressbar.set_visible(False)
                self.close()

            def display_post_clean_operation_dialog(self):
                if self.retcode.value == 0:
                    title = "SD-card Cleaning Completed"
                    content = (
                        "Your SD-card ({}) has been wiped.\n\n"
                        "You now need to unplug then replug your device.\n"
                        "Once done, come back and hit the refresh button."
                    ).format(sd_card)
                else:
                    title = "SD-card Cleaning Failed"
                    content = (
                        "You SD-card HAS NOT been wiped.\n\n"
                        "Please use a different tool to clean it."
                    )

                msg_box = Gtk.MessageDialog(
                    self.parent, None, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, title
                )

                msg_box.format_secondary_text(content)
                msg_box.set_modal(True)
                msg_box.run()
                msg_box.destroy()
                self.close()
                self.parent_ui.sd_card_refresh_button_clicked("")

        dialog = SDCleanDialog(self.component.window, self)
        ret = dialog.run()
        if ret == Gtk.ResponseType.OK:
            dialog.start_clean_operation()
        else:
            dialog.close()
            self.sd_card_refresh_button_clicked("")

    def installation_done(self, error):
        ok = error is None
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
        dialog = ShortDialog(
            self.component.run_window,
            (
                Gtk.STOCK_CANCEL,
                Gtk.ResponseType.CANCEL,
                Gtk.STOCK_OK,
                Gtk.ResponseType.OK,
            ),
            "Are you sure you want to abort the installation ?\nyou will not be able to resume.",
        )
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            self.cancel_run()

        dialog.destroy()

    def run_new_install_button_clicked(self, widget):
        self.logger.reset()
        self.component.run_window.hide()
        self.component.window.show()

    def display_error_message(self, title, message=None, parent=None, flags=None):
        if parent is None:
            parent = self.component.window
        dialog = Gtk.MessageDialog(
            parent, flags, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, title
        )
        if message is not None:
            dialog.format_secondary_text(message)
        dialog.set_modal(True)
        dialog.run()
        dialog.destroy()

    def activate_menu_config(self, widget, for_save=False):
        home_path = os.environ["HomePath" if sys.platform == "win32" else "HOME"]

        if not for_save and not self.ensure_catalogs():
            return

        def _save(dialog):
            filename = (
                dialog.get_filename()
                if dialog.get_filename().endswith(".json")
                else "{}.json".format(dialog.get_filename())
            )
            try:
                with open(filename, "w", encoding="utf-8") as fd:
                    json.dump(self.get_config(), fd, indent=4)
            except Exception:
                self.display_error_message(
                    "Unable to save JSON configuration to file",
                    "Please check that the path is reachable and writable.",
                )

        def _load(dialog):
            try:
                with open(dialog.get_filename(), "r") as fd:
                    config = json.load(fd)
            except Exception:
                self.display_error_message(
                    "Unable to load JSON configuration",
                    "Please check that the file is readable "
                    "and in proper JSON format",
                )
            else:
                self.set_config(config)

        if for_save:
            title = "Select a file to save Kiwix Hotspot config to"
            action = Gtk.FileChooserAction.SAVE
            on_accept = _save
        else:
            title = "Select Kiwix Hotspot config file to load"
            action = Gtk.FileChooserAction.OPEN
            on_accept = _load

        if hasattr(Gtk, "FileChooserNative"):
            dialog = Gtk.FileChooserNative.new(
                title,
                self.component.window,  # make it tied to parent and modal
                action,
                "OK",
                "Cancel",
            )
            dialog.set_current_folder(home_path)
        else:
            dialog = Gtk.FileChooserDialog(
                title,
                self.component.window,
                action=action,
                buttons=(
                    Gtk.STOCK_CANCEL,
                    Gtk.ResponseType.CANCEL,
                    Gtk.STOCK_OK,
                    Gtk.ResponseType.ACCEPT,
                ),
            )
            dialog.set_current_folder(home_path)
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
        if config.get("project_name") is not None:
            self.component.project_name_entry.set_text(config.get("project_name"))

        # language
        try:
            value = dict(data.hotspot_languages)[config["language"]]
            item_tuple = (config["language"], value)
            item_id = data.hotspot_languages.index(item_tuple)
        except KeyError:
            pass
        else:
            self.component.language_combobox.set_active(item_id)

        # timezone
        try:
            item_id = [
                row_id
                for row_id, row_data in enumerate(self.component.timezone_tree_store)
                if row_data[0] == config["timezone"]
            ][0]
        except (KeyError, IndexError):
            pass
        else:
            self.component.timezone_combobox.set_active(item_id)

        # wifi (previous format)
        if "wifi" in config.keys() and isinstance(config["wifi"], dict):
            if "protected" in config["wifi"].keys():
                self.component.wifi_password_switch.set_active(
                    not bool(config["wifi"]["protected"])
                )
            if "password" in config["wifi"].keys():
                self.component.wifi_password_entry.set_text(config["wifi"]["password"])
        # wifi (new format)
        if "wifi_password" in config.keys():
            self.component.wifi_password_switch.set_active(
                config["wifi_password"] is None
            )
            if config["wifi_password"] is not None:
                self.component.wifi_password_entry.set_text(config["wifi_password"])

        # admin account
        if "admin_account" in config.keys() and isinstance(
            config["admin_account"], dict
        ):
            for key, arg_key in {"login": "login", "password": "pwd"}.items():
                if config["admin_account"].get(key) is not None:
                    getattr(
                        self.component, "admin_account_{}_entry".format(arg_key)
                    ).set_text(config["admin_account"][key])

        # branding
        if "branding" in config.keys() and isinstance(config["branding"], dict):
            for key in ("logo", "favicon", "css"):
                if config["branding"].get(key) is not None:
                    try:
                        fpath = b64decode(
                            fname=config["branding"][key]["fname"],
                            data=config["branding"][key]["data"],
                            to=tempfile.mkdtemp(),
                        )
                    except Exception:
                        pass
                    else:
                        getattr(self.component, "{}_chooser".format(key)).set_filename(
                            fpath
                        )

        # build_dir
        if config.get("build_dir") is not None:
            self.component.build_path_chooser.set_filename(
                os.path.abspath(config["build_dir"])
            )

        # size
        if config.get("size") is not None:
            try:
                size = (
                    humanfriendly.parse_size(config["size"])
                    if isinstance(config["size"], str)
                    else config["size"]
                )
                size = int(size / ONE_GB)
            except Exception:
                size = None
            if size is not None:
                sd_size = min(
                    filter(lambda x: x >= size, data.sdcard_sizes),
                    default=data.sdcard_sizes[-1],
                )
                self.component.size_combobox.set_active(
                    data.sdcard_sizes.index(sd_size)
                )

        # content
        if "content" in config.keys() and isinstance(config["content"], dict):

            # langs-related contents
            for key in ("kalite", "wikifundi"):
                if key in config["content"].keys() and isinstance(
                    config["content"][key], list
                ):
                    for lang, button in getattr(
                        self, "iter_{}_check_button".format(key)
                    )():
                        button.set_active(lang in config["content"][key])

            # boolean contents (switches)
            for key in ("edupi", "aflatoun"):
                if config["content"].get(key) is not None:
                    getattr(self.component, "{}_switch".format(key)).set_active(
                        config["content"][key]
                    )

            # edupi resources
            if config["content"].get("edupi_resources") is not None:
                rsc = config["content"].get("edupi_resources")
                if isremote(rsc):
                    self.component.edupi_resources_url_entry.set_text(str(rsc))
                else:
                    self.component.edupi_resources_chooser.set_filename(str(rsc))

            if "zims" in config["content"].keys() and isinstance(
                config["content"]["zims"], list
            ):

                nb_zims = len(self.component.zim_tree_view.get_model())
                index = 0
                nb_selected = 0
                while index < (nb_zims - nb_selected):
                    try:
                        zim = self.component.zim_tree_view.get_model()[index]
                    except IndexError:
                        break
                    selected = zim[0] in config["content"]["zims"]

                    self.component.zim_tree_view.get_model()[index][8] = selected

                    if selected:
                        nb_selected += 1
                    else:
                        index += 1
                    continue

                self.update_free_space()

    def get_config(self):
        try:
            language_id = self.component.language_combobox.get_active()
            language = data.hotspot_languages[language_id][0]
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
            lang
            for lang, button in self.iter_kalite_check_button()
            if button.get_active()
        ]

        wikifundi_active_langs = [
            lang
            for lang, button in self.iter_wikifundi_check_button()
            if button.get_active()
        ]

        try:
            size = data.sdcard_sizes[self.component.size_combobox.get_active()] * ONE_GB
        except Exception:
            size = None

        branding = {}
        for key in ("logo", "favicon", "css"):
            fpath = getattr(self.component, "{}_chooser".format(key)).get_filename()
            if fpath is not None and os.path.exists(fpath):
                try:
                    branding[key] = {
                        "fname": os.path.basename(fpath),
                        "data": b64encode(fpath),
                    }
                except Exception:
                    pass

        return OrderedDict(
            [
                ("project_name", self.component.project_name_entry.get_text()),
                ("language", language),
                ("timezone", timezone),
                (
                    "wifi_password",
                    None
                    if self.component.wifi_password_switch.get_active()
                    else self.component.wifi_password_entry.get_text(),
                ),
                (
                    "admin_account",
                    OrderedDict(
                        [
                            (
                                "login",
                                self.component.admin_account_login_entry.get_text(),
                            ),
                            (
                                "password",
                                self.component.admin_account_pwd_entry.get_text(),
                            ),
                        ]
                    ),
                ),
                (
                    "build_dir",
                    relpathto(self.component.build_path_chooser.get_filename()),
                ),
                ("size", None if size is None else human_readable_size(size, False)),
                (
                    "content",
                    OrderedDict(
                        [
                            ("zims", zim_install),  # content-ids list
                            ("kalite", kalite_active_langs),  # languages list
                            ("wikifundi", wikifundi_active_langs),  # languages list
                            ("aflatoun", self.component.aflatoun_switch.get_active()),
                            ("edupi", self.component.edupi_switch.get_active()),
                            ("edupi_resources", edupi_resources),
                        ]
                    ),
                ),
                ("branding", branding),
            ]
        )

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

    def get_sd_card(self):
        if self.component.output_stack.get_visible_child_name() == "sd_card":
            sd_card_id = self.component.sd_card_combobox.get_active()

            if sd_card_id == -1:
                return None
            else:
                device_index = sd_card_info.get_device_index()
                return self.component.sd_card_list_store[sd_card_id][device_index]
        return None

    def run_installation_button_clicked(self, button):
        all_valid = True

        # capture input
        project_name = self.component.project_name_entry.get_text()
        language = data.hotspot_languages[
            self.component.language_combobox.get_active()
        ][0]
        timezone = self.component.timezone_tree_store[
            self.component.timezone_combobox.get_active()
        ][0]
        wifi_pwd = (
            None
            if self.component.wifi_password_switch.get_state()
            else self.component.wifi_password_entry.get_text()
        )
        admin_login = self.component.admin_account_login_entry.get_text()
        admin_pwd = self.component.admin_account_pwd_entry.get_text()
        zim_install = [zim[0] for zim in self.component.zim_list_store if zim[8]]

        # validate inputs
        valid_project_name, valid_language, valid_timezone, valid_wifi_pwd, valid_admin_login, valid_admin_pwd = check_user_inputs(
            project_name=self.component.project_name_entry.get_text(),
            language=data.hotspot_languages[
                self.component.language_combobox.get_active()
            ][0],
            timezone=self.component.timezone_tree_store[
                self.component.timezone_combobox.get_active()
            ][0],
            wifi_pwd=None
            if self.component.wifi_password_switch.get_state()
            else self.component.wifi_password_entry.get_text(),
            admin_login=self.component.admin_account_login_entry.get_text(),
            admin_pwd=self.component.admin_account_pwd_entry.get_text(),
        )

        # project name
        validate_label(self.component.project_name_label, valid_project_name)
        self.component.project_name_constraints_revealer.set_reveal_child(
            not valid_project_name
        )
        all_valid = all_valid and valid_project_name

        # language
        validate_label(self.component.language_label, valid_language)
        all_valid = all_valid and valid_language

        # timezone
        validate_label(self.component.timezone_label, valid_timezone)
        all_valid = all_valid and valid_timezone

        # wifi passwd
        validate_label(self.component.wifi_password_label, valid_wifi_pwd)
        self.component.wifi_password_constraints_revealer.set_reveal_child(
            not valid_wifi_pwd
        )
        all_valid = all_valid and valid_wifi_pwd

        # admin account
        validate_label(self.component.admin_account_login_label, valid_admin_login)
        validate_label(self.component.admin_account_pwd_label, valid_admin_pwd)
        self.component.admin_account_login_constraints_revealer.set_reveal_child(
            not valid_admin_login
        )
        self.component.admin_account_pwd_constraints_revealer.set_reveal_child(
            not valid_admin_pwd
        )
        all_valid = all_valid and valid_admin_login and valid_admin_pwd

        output_size = self.get_output_size()

        sd_card = self.get_sd_card()
        if self.component.output_stack.get_visible_child_name() == "sd_card":
            condition = sd_card is not None
            validate_label(self.component.sd_card_label, condition)
            all_valid = all_valid and condition

            # check that SD card has a single partition (clean state)
            condition = sd_has_single_partition(sd_card, self.logger)
            validate_label(self.component.sd_card_label, condition)
            validate_label(self.component.sd_card_error_label, condition)
            self.component.sd_card_error_label.set_visible(not condition)
            all_valid = all_valid and condition
        else:
            condition = output_size > 0
            validate_label(self.component.size_label, condition)
            all_valid = all_valid and condition

        condition = self.update_free_space() >= 0
        validate_label(self.component.free_space_name_label, condition)
        all_valid = all_valid and condition

        kalite_active_langs = [
            lang
            for lang, button in self.iter_kalite_check_button()
            if button.get_active()
        ]
        if len(kalite_active_langs) != 0:
            kalite = kalite_active_langs
        else:
            kalite = None

        wikifundi_active_langs = [
            lang
            for lang, button in self.iter_wikifundi_check_button()
            if button.get_active()
        ]
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
        condition = (
            build_dir is not None
            and os.path.exists(build_dir)
            and os.path.isdir(build_dir)
        )
        validate_label(self.component.build_path_chooser_label, condition)
        all_valid = all_valid and condition

        # Check if there is enough space in build_dir to build image
        if condition:
            free_space = get_free_space_in_dir(build_dir)
            remaining_space = free_space - output_size
            if remaining_space < 0:
                self.component.space_error_image_location_label.set_text(build_dir)
                self.component.space_error_total_space_required_label.set_text(
                    human_readable_size(output_size)
                )
                self.component.space_error_space_available_label.set_text(
                    human_readable_size(free_space)
                )
                self.component.space_error_space_missing_label.set_text(
                    human_readable_size(-remaining_space)
                )

                self.component.space_error_window.show()
                all_valid = False

        all_valid = all_valid and self.ensure_connection() and self.ensure_catalogs()

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
                    admin_account={"login": admin_login, "pwd": admin_pwd},
                    done_callback=lambda error: GLib.idle_add(
                        self.installation_done, error
                    ),
                    shrink=True,
                )

            self.component.window.hide()
            self.reset_run_window()
            self.component.run_window.show()
            threading.Thread(target=target, daemon=True).start()

    def on_sdcard_selection_change(self, button):
        has_card = self.component.sd_card_combobox.get_active() != -1
        self.component.clean_sd_button.set_visible(has_card)

        # remove warnings on combo change
        validate_label(self.component.sd_card_label, True)
        validate_label(self.component.sd_card_error_label, True)
        self.component.sd_card_error_label.set_visible(False)

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
            items = [
                info["typ"](device[info["name"]]) for info in sd_card_info.informations
            ]
            self.component.sd_card_list_store.append(items)
            device_name = str(device["device"]).rstrip("\0")
            if device_name == selected_device:
                self.component.sd_card_combobox.set_active(id)

    def zim_choose_content_button_clicked(self, button):
        if self.ensure_catalogs():
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
            aflatoun_languages=["fr", "en"] if aflatoun else [],
        )
        try:
            required_image_size = get_required_image_size(collection)
        except FileNotFoundError:
            self.display_error_message(
                "Free Space Calculation Error",
                "Unable to calculate free space due to a missing file.\n"
                "Please, check if the EduPi resources file is still there.",
                self.component.window,
            )
            return -1

        return self.get_output_size() - required_image_size

    def update_free_space(self):
        free_space = self.get_free_space()
        human_readable_free_space = human_readable_size(free_space)
        self.component.free_space_label1.set_text(human_readable_free_space)
        self.component.free_space_label2.set_text(human_readable_free_space)
        condition = free_space >= 0
        validate_label(self.component.free_space_label1, condition)
        validate_label(self.component.free_space_label2, condition)

        # size should be at least base_image size
        size = self.get_output_size()
        validate_label(
            self.component.size_combobox,
            size >= get_content("hotspot_master_image")["expanded_size"],
        )

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
                size = int(
                    self.component.sd_card_list_store[sd_card_id][get_size_index]
                )
        else:
            try:
                size = get_adjusted_image_size(
                    data.sdcard_sizes[self.component.size_combobox.get_active()]
                    * ONE_GB
                )
            except Exception:
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


Application()

run()
