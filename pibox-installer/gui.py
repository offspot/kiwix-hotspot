import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf
from backend import catalog
from run_installation import run_installation
import pytz
import tzlocal
import os
import sys
import threading
from util import CancelEvent
import sd_card_list
from util import human_readable_size
from datetime import datetime
import data
import langcodes

HEX_RED = 0xFF757500
HEX_GREEN = 0x75FF7500

KALITE_SIZES = {
    "fr": 10737418240,
    "es": 19327352832,
    "en": 41875931136,
}

class Logger:
    def __init__(self, text_buffer, step_label):
        self.text_buffer = text_buffer
        self.step_label = step_label
        self.step_tag = self.text_buffer.create_tag("step", foreground="blue")
        self.err_tag = self.text_buffer.create_tag("err", foreground="red")

    def step(self, step):
        GLib.idle_add(self.main_thread_step, step)

    def err(self, err):
        GLib.idle_add(self.main_thread_err, err)

    def raw_std(self, std):
        GLib.idle_add(self.main_thread_raw_std, std)

    def std(self, std):
        GLib.idle_add(self.main_thread_std, std)

    def main_thread_step(self, text):
        text_iter = self.text_buffer.get_end_iter()
        self.text_buffer.insert_with_tags(text_iter, text + "\n", self.step_tag)
        self.step_label.set_text(text)

    def main_thread_err(self, text):
        text_iter = self.text_buffer.get_end_iter()
        self.text_buffer.insert_with_tags(text_iter, text + "\n", self.err_tag)

    def main_thread_raw_std(self, text):
        text_iter = self.text_buffer.get_end_iter()
        self.text_buffer.insert(text_iter, text)

    def main_thread_std(self, text):
        text_iter = self.text_buffer.get_end_iter()
        self.text_buffer.insert(text_iter, text + "\n")

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
    color_invalid = Gdk.Color(65535, 30000, 30000)
    if condition:
        label.modify_bg(Gtk.StateFlags.NORMAL)
    else:
        label.modify_bg(Gtk.StateFlags.NORMAL, color_invalid)

class Application:
    def __init__(self, catalog):
        self.catalog = catalog

        builder = Gtk.Builder()
        builder.add_from_file(data.ui_glade)

        self.component = Component(builder)
        self.cancel_event = CancelEvent()
        self.logger = Logger(self.component.run_text_view.get_buffer(), self.component.run_step_label)

        # main window
        self.component.window.connect("delete-event", Gtk.main_quit)

        # wifi password
        self.component.wifi_password_switch.connect("notify::active", lambda switch, state: self.component.wifi_password_revealer.set_reveal_child(switch.get_active()))

        # timezone
        default_id = -1
        local_tz = tzlocal.get_localzone()
        for id, timezone in enumerate(pytz.common_timezones):
            if timezone == "UTC" and default_id == -1:
                default_id = id
            if pytz.timezone(timezone) == local_tz:
                default_id = id
            self.component.timezone_tree_store.append(None, [timezone])

        renderer = Gtk.CellRendererText()
        self.component.timezone_combobox.pack_start(renderer, True)
        self.component.timezone_combobox.add_attribute(renderer, "text", 0)
        self.component.timezone_combobox.set_active(default_id)

        # output
        self.component.sd_card_combobox.connect("changed", lambda _: self.update_free_space())
        self.component.sd_card_refresh_button.connect("clicked", self.sd_card_refresh_button_clicked)
        self.component.output_stack.connect("notify::visible-child", lambda switch, state: self.update_free_space())
        self.component.size_entry.connect("changed", lambda _: self.update_free_space())

        types = [info["typ"] for info in sd_card_list.informations]
        self.component.sd_card_list_store = Gtk.ListStore(*types)
        self.component.sd_card_combobox.set_model(self.component.sd_card_list_store)

        for counter, _ in enumerate(filter(lambda info: info["show"], sd_card_list.informations)):
            info = Gtk.CellRendererText()
            self.component.sd_card_combobox.pack_start(info, True)
            self.component.sd_card_combobox.add_attribute(info, "text", counter)

        # done window
        self.component.done_window.set_transient_for(self.component.run_window)
        self.component.done_window.set_default_size(320, 240)
        self.component.done_window.set_modal(True)
        self.component.done_window_ok_button.connect("clicked", self.done_window_ok_button_clicked)

        # run window
        self.component.run_installation_button.connect("clicked", self.run_installation_button_clicked)
        self.component.run_window.connect("delete-event", self.run_window_delete_event)
        self.component.run_window.set_default_size(640, 480)
        self.component.run_text_view.get_buffer().connect("modified-changed", self.run_text_view_scroll_down)
        self.component.run_abort_done_button.connect("clicked", self.run_abort_done_button_clicked)
        self.component.run_copy_log_to_clipboard_button.connect("clicked", self.run_copy_log_to_clipboard_button_clicked)

        # zim content
        self.component.zim_choose_content_button.connect("clicked", self.zim_choose_content_button_clicked)

        self.component.zim_list_store = Gtk.ListStore(str, str, str, str, str, str, str, str, bool, str, bool, GdkPixbuf.Pixbuf);
        self.component.zim_list_store.set_sort_column_id(1, Gtk.SortType.ASCENDING)

        languages = set()

        for one_catalog in catalog:
            for (key, value) in one_catalog["all"].items():
                name = value["name"]
                url = value["url"]
                description = value.get("description") or "none"
                formatted_size = human_readable_size(int(value["size"]))
                size = str(value["size"])
                language = langcodes.Language.get(value.get("language") or "none").language_name()
                typ = value["type"]
                version = str(value["version"])
                fit = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 32, 16)
                fit.fill(HEX_GREEN)

                self.component.zim_list_store.append([key, name, url, description, formatted_size, language, typ, version, False, size, True, fit])
                languages.add(language)

        self.component.zim_choosen_filter = self.component.zim_list_store.filter_new()
        self.component.zim_choosen_filter.set_visible_func(self.zim_choosen_filter_func)
        self.component.zim_choosen_tree_view.set_model(self.component.zim_choosen_filter)
        self.component.zim_choosen_tree_view.get_selection().set_mode(Gtk.SelectionMode(0))

        renderer_text = Gtk.CellRendererText()
        column_text = Gtk.TreeViewColumn("Id", renderer_text, text=0)
        self.component.zim_choosen_tree_view.append_column(column_text)

        # zim window
        self.component.zim_window.set_transient_for(self.component.window)
        self.component.zim_window.set_modal(True)
        self.component.zim_window.set_default_size(1024, 650)

        self.component.zim_window_done_button.connect("clicked", self.zim_done_button_clicked)
        self.component.zim_tree_view.connect("row-activated", self.available_zim_clicked)
        self.component.choosen_zim_tree_view.connect("row-activated", self.choosen_zim_clicked)

        ## zim window available tree view
        self.component.zim_tree_view.set_model(self.component.zim_list_store)

        renderer_pixbuf = Gtk.CellRendererPixbuf().new()
        column_pixbuf = Gtk.TreeViewColumn("Fit", renderer_pixbuf, pixbuf=11)
        self.component.zim_tree_view.append_column(column_pixbuf)

        renderer_text = Gtk.CellRendererText()
        column_text = Gtk.TreeViewColumn("Name", renderer_text, text=1)
        self.component.zim_tree_view.append_column(column_text)
        column_text = Gtk.TreeViewColumn("Size", renderer_text, text=4)
        self.component.zim_tree_view.append_column(column_text)
        column_text = Gtk.TreeViewColumn("Description", renderer_text, text=3)
        self.component.zim_tree_view.append_column(column_text)

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

        choosen_zim_filter = self.component.zim_list_store.filter_new()
        choosen_zim_filter.set_visible_func(self.choosen_zim_filter_func)
        self.component.choosen_zim_tree_view.set_model(choosen_zim_filter)

        # zim window language check buttons
        for language in sorted(languages):
            button = Gtk.CheckButton.new_with_label(language)
            button.set_active(True)

            button.connect("toggled", self.toggle_column(5, 10, language))
            self.component.zim_languages_box.pack_start(button, False, True, 0)

        self.component.zim_languages_box.show_all()

        # kalite
        self.component.kalite_switch.connect("notify::active", lambda switch, state: self.component.kalite_revealer.set_reveal_child(switch.get_active()))
        for lang, button in self.iter_kalite_check_button():
            button.connect("toggled", lambda button: self.update_free_space())

        self.refresh_disk_list()
        self.update_free_space()

        self.component.window.show()

    def iter_kalite_check_button(self):
        return [("fr", self.component.kalite_fr_check_button),
                ("en", self.component.kalite_en_check_button),
                ("es", self.component.kalite_es_check_button)]

    def done_window_ok_button_clicked(self, widget):
        self.component.done_window.hide()

    def installation_done(self, error):
        if error != None:
            self.component.done_label.set_text("Installation failed")
            validate_label(self.component.done_label, False)
        self.component.done_window.show()
        self.component.run_abort_done_button.set_label("Back")
        self.component.run_spinner.stop()

    def run_text_view_scroll_down(self, widget):
        text_buffer = self.component.run_text_view.get_buffer()
        text_buffer.set_modified(False)

        end = text_buffer.get_end_iter()
        end = self.component.run_text_view.get_buffer().get_end_iter()
        end.backward_line()

        self.component.run_text_view.scroll_to_iter(end, 0, True, 0, 1.)

    def run_window_delete_event(self, widget, path):
        self.cancel_event.cancel()
        Gtk.main_quit()

    def run_abort_done_button_clicked(self, widget):
        self.component.run_window.close()

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
        condition = project_name != ""
        validate_label(self.component.project_name_label, condition)
        all_valid = all_valid and condition

        timezone_id = self.component.timezone_combobox.get_active()
        timezone = self.component.timezone_tree_store[timezone_id][0]
        condition = timezone_id != -1
        validate_label(self.component.timezone_label, condition)
        all_valid = all_valid and condition

        if self.component.wifi_password_switch.get_state():
            wifi_pwd = self.component.wifi_password_entry.get_text()
        else:
            wifi_pwd = None

        zim_install = []
        for zim in self.component.zim_list_store:
            if zim[8]:
                zim_install.append(zim[0])

        if self.component.output_stack.get_visible_child_name() == "sd_card":
            sd_card_id = self.component.sd_card_combobox.get_active()
            condition = sd_card_id != -1
            validate_label(self.component.sd_card_label, condition)
            all_valid = all_valid and condition

            if sd_card_id == -1:
                sd_card = None
            else:
                device_index = sd_card_list.get_device_index()
                sd_card = self.component.sd_card_list_store[sd_card_id][device_index]
            output_file = False
            size = self.get_output_size()
        else:
            sd_card = None
            size = self.get_output_size()
            today = datetime.today().strftime('%Y_%m_%d-%H_%M_%S')
            filename = "pibox-{}.img".format(today)
            output_dir = os.path.join(os.path.expanduser('~'), 'Desktop')
            if not os.path.isdir(output_dir):
                output_dir = os.path.expanduser('~')
            output_file = os.path.join(output_dir, filename)

            condition = size > 0
            validate_label(self.component.size_label, condition)
            all_valid = all_valid and condition

        condition = self.update_free_space() >= 0
        validate_label(self.component.free_space_name_label, condition)
        all_valid = all_valid and condition

        if self.component.kalite_switch.get_state():
            kalite = []
            for lang, button in self.iter_kalite_check_button():
                kalite.append(lang)
        else:
            kalite = None


        if all_valid:
            def target():
                run_installation(
                        name=project_name,
                        timezone=timezone,
                        wifi_pwd=wifi_pwd,
                        kalite=kalite,
                        zim_install=zim_install,
                        size=size,
                        logger=self.logger,
                        cancel_event=self.cancel_event,
                        sd_card=sd_card,
                        output_file=output_file,
                        done_callback=lambda error: GLib.idle_add(self.installation_done, error))

            self.component.window.hide()
            self.component.run_window.show()
            threading.Thread(target=target, daemon=True).start()

    def sd_card_refresh_button_clicked(self, button):
        self.refresh_disk_list()
        self.update_free_space()

    def refresh_disk_list(self):
        self.component.sd_card_list_store.clear()
        for device in sd_card_list.get_list():
            items = [info["typ"](device[info["name"]]) for info in sd_card_list.informations]
            self.component.sd_card_list_store.append(items)

    def zim_choose_content_button_clicked(self, button):
        self.component.zim_window.show()

    def zim_choosen_filter_func(self, model, iter, data):
        return model[iter][8]

    def get_free_space(self):
        # TODO: compute actual space used with empty install
        used_space = 2 * 2**30 # space of raspbian with ideascube without content
        for zim in self.component.zim_list_store:
            if zim[8]:
                used_space += int(zim[9])
        if self.component.kalite_switch.get_state():
            for lang, button in self.iter_kalite_check_button():
                if button.get_active():
                    used_space += KALITE_SIZES[lang]
        return self.get_output_size() - used_space

    def update_free_space(self):
        free_space = self.get_free_space()
        human_readable_free_space = human_readable_size(free_space)
        self.component.free_space_label1.set_text(human_readable_free_space)
        self.component.free_space_label2.set_text(human_readable_free_space)
        condition = free_space >= 0
        validate_label(self.component.free_space_label1, condition)
        validate_label(self.component.free_space_label2, condition)
        for row in self.component.zim_list_store:
            if free_space - int(row[9]) >= 0:
                row[11].fill(HEX_GREEN)
            else:
                row[11].fill(HEX_RED)
        return free_space

    def get_output_size(self):
        if self.component.output_stack.get_visible_child_name() == "sd_card":
            sd_card_id = self.component.sd_card_combobox.get_active()
            if sd_card_id == -1:
                size = -1
            else:
                get_size_index = sd_card_list.get_size_index()
                size = int(self.component.sd_card_list_store[sd_card_id][get_size_index])
        else:
            try:
                size = int(self.component.size_entry.get_text()) * 2**30
            except:
                size = -1

        return size

    def toggle_column(self, name_column, filter_column, name):
        def toggle(button):
            for item in self.component.zim_list_store:
                if item[name_column] == name:
                    item[filter_column] = button.get_active()
        return toggle

    def available_zim_clicked(self, tree_view, path, column):
        tree_view.get_model()[path][8] = True
        self.update_free_space()

    def choosen_zim_clicked(self, tree_view, path, column):
        tree_view.get_model()[path][8] = False
        self.update_free_space()

    def zim_done_button_clicked(self, widget):
        self.component.zim_window.hide()

    def zim_filter_func(self, model, iter, data):
        return model[iter][10] and not model[iter][8]

    def choosen_zim_filter_func(self, model, iter, data):
        return model[iter][8]

catalog = catalog.get_catalogs()
Application(catalog)
Gtk.main()
