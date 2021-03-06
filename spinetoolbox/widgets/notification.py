######################################################################################################################
# Copyright (C) 2017-2021 Spine project consortium
# This file is part of Spine Toolbox.
# Spine Toolbox is free software: you can redistribute it and/or modify it under the terms of the GNU Lesser General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option)
# any later version. This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General
# Public License for more details. You should have received a copy of the GNU Lesser General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.
######################################################################################################################

"""
Contains a notification widget.

:author: P. Savolainen (VTT)
:date: 12.12.2019
"""

from PySide2.QtWidgets import QWidget, QLabel, QHBoxLayout, QGraphicsOpacityEffect, QLayout, QSizePolicy
from PySide2.QtCore import Qt, Slot, QTimer, QPropertyAnimation, Property, QObject
from PySide2.QtGui import QFont


class Notification(QWidget):
    """Custom pop-up notification widget with fade-in and fade-out effect."""

    def __init__(self, parent, txt, anim_duration=500, life_span=None, alignment=Qt.AlignCenter):
        """

        Args:
            parent (QWidget): Parent widget
            txt (str): Text to display in notification
            anim_duration (int): Duration of the animation in msecs
            life_span (int): How long does the notification stays in place in msecs
        """
        super().__init__()
        if life_span is None:
            word_count = len(txt.split(" "))
            mspw = 60000 / 140  # Assume people can read ~140 words per minute
            life_span = mspw * word_count
        self.setWindowFlags(Qt.Popup)
        self.setParent(parent)
        self._parent = parent
        self.label = QLabel(txt)
        self.label.setMaximumSize(parent.size())
        self.label.setAlignment(alignment)
        self.label.setWordWrap(True)
        self.label.setMargin(8)
        self.label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        font = QFont()
        font.setBold(True)
        self.label.setFont(font)
        layout = QHBoxLayout()
        layout.addWidget(self.label)
        layout.setSizeConstraint(QLayout.SetMinimumSize)
        layout.setContentsMargins(1, 0, 1, 0)
        self.setLayout(layout)
        self.adjustSize()
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setAttribute(Qt.WA_TranslucentBackground)
        ss = (
            "QWidget{background-color: rgba(255, 194, 179, 0.9);"
            "border-width: 2px;"
            "border-color: #ffebe6;"
            "border-style: groove; border-radius: 8px;}"
        )
        self.setStyleSheet(ss)
        self.setAcceptDrops(True)
        self.effect = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self.effect)
        self.effect.setOpacity(0.0)
        self._opacity = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(life_span)
        self.timer.timeout.connect(self.start_self_destruction)
        # Fade in animation
        self.fade_in_anim = QPropertyAnimation(self, b"opacity")
        self.fade_in_anim.setDuration(anim_duration)
        self.fade_in_anim.setStartValue(0.0)
        self.fade_in_anim.setEndValue(1.0)
        self.fade_in_anim.valueChanged.connect(self.update_opacity)
        self.fade_in_anim.finished.connect(self.timer.start)
        # Fade out animation
        self.fade_out_anim = QPropertyAnimation(self, b"opacity")
        self.fade_out_anim.setDuration(anim_duration)
        self.fade_out_anim.setStartValue(1.0)
        self.fade_out_anim.setEndValue(0)
        self.fade_out_anim.valueChanged.connect(self.update_opacity)
        self.fade_out_anim.finished.connect(self.close)
        # Start fade in animation
        self.fade_in_anim.start(QPropertyAnimation.DeleteWhenStopped)

    def show(self):
        # Move to the top right corner of the parent
        super().show()
        x = self._parent.size().width() - self.width() - 2
        self.move(x, self.pos().y())

    def get_opacity(self):
        """opacity getter."""
        return self._opacity

    def set_opacity(self, op):
        """opacity setter."""
        self._opacity = op

    @Slot(float)
    def update_opacity(self, value):
        """Updates graphics effect opacity."""
        self.effect.setOpacity(value)

    def start_self_destruction(self):
        """Starts fade-out animation and closing of the notification."""
        self.fade_out_anim.start(QPropertyAnimation.DeleteWhenStopped)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def enterEvent(self, e):
        super().enterEvent(e)
        self.start_self_destruction()

    def dragEnterEvent(self, e):
        super().dragEnterEvent(e)
        self.start_self_destruction()

    def remaining_time(self):
        if self.timer.isActive():
            return self.timer.remainingTime()
        if self.fade_out_anim.state() == QPropertyAnimation.Running:
            return 0
        return self.timer.interval()

    opacity = Property(float, get_opacity, set_opacity)


class LinkNotification(Notification):
    """A notification that may have a link."""

    def __init__(self, *args, open_link=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        if open_link is None:
            self.label.setOpenExternalLinks(True)
        else:
            self.label.linkActivated.connect(open_link)

    def enterEvent(self, e):
        """Pauses timer as the mouse hovers the notification."""
        QWidget.enterEvent(self, e)
        if self.remaining_time():
            self.timer.stop()

    def leaveEvent(self, e):
        """Resumes timer after the mouse leaves the notification."""
        QWidget.leaveEvent(self, e)
        remaining_time = self.remaining_time()
        if remaining_time:
            self.timer.start(remaining_time)


class NotificationStack(QObject):
    def __init__(self, parent, anim_duration=500, life_span=None):
        super().__init__()
        self._parent = parent
        self._anim_duration = anim_duration
        self._life_span = life_span
        self.notifications = list()

    def push_notification(self, notification):
        """Pushes a notification to the stack with the given text."""
        offset = sum((x.height() for x in self.notifications), 0)
        additional_life_span = 0.8 * self.notifications[-1].remaining_time() if self.notifications else 0
        notification.timer.setInterval(notification.timer.interval() + additional_life_span)
        notification.move(notification.pos().x(), offset)
        notification.destroyed.connect(
            lambda obj=None, n=notification, h=notification.height(): self.handle_notification_destroyed(n, h)
        )
        self.notifications.append(notification)
        notification.show()

    def push(self, txt):
        notification = Notification(self._parent, txt, anim_duration=self._anim_duration, life_span=self._life_span)
        self.push_notification(notification)

    def push_link(self, txt, open_link=None):
        notification = LinkNotification(
            self._parent, txt, anim_duration=self._anim_duration, life_span=self._life_span, open_link=open_link
        )
        self.push_notification(notification)

    def handle_notification_destroyed(self, notification, height):
        """Removes from the stack the given notification and move up
        subsequent ones.
        """
        i = self.notifications.index(notification)
        self.notifications.remove(notification)
        for n in self.notifications[i:]:
            n.move(n.pos().x(), n.pos().y() - height)
