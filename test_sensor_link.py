"""
Tests for sensor_link.py - no hardware or network needed.

    python -m unittest discover tests
"""

import os
import socket
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sensor_link as sl  # noqa: E402


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class FakeSocket:
    """Stands in for the UDP socket: nothing to receive, records what is sent."""
    def __init__(self):
        self.sent = []

    def setblocking(self, flag):
        pass

    def recvfrom(self, size):
        raise BlockingIOError

    def sendto(self, data, address):
        self.sent.append((data, address))

    def close(self):
        pass


def make_link():
    clock = FakeClock()
    sock = FakeSocket()
    return sl.SensorLink(clock=clock, sock=sock), clock, sock


def feed_all(link, mm_by_sensor, times=sl.MEDIAN_WINDOW, ip="10.0.0.{}"):
    for _ in range(times):
        for sid, mm in mm_by_sensor.items():
            link.feed(f"{sid},{mm}".encode(), (ip.format(sid), 40000))
    link.poll()


class ParseTests(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(sl.parse_packet(b"1,850"), (1, 85.0))

    def test_no_echo_and_out_of_range(self):
        self.assertEqual(sl.parse_packet(b"2,-1")[1], float("inf"))
        self.assertEqual(sl.parse_packet(b"2,9000")[1], float("inf"))

    def test_garbage_ignored(self):
        for bad in (b"", b"hello", b"7,100", b"1", b"\xff\xfe"):
            self.assertIsNone(sl.parse_packet(bad), bad)

    def test_wireless_doc_fixed_values(self):
        # Step 11 of the wireless plan: 100 / 200 / 300 mm.
        self.assertEqual(sl.parse_packet(b"1,100"), (1, 10.0))
        self.assertEqual(sl.parse_packet(b"3,300"), (3, 30.0))


class RowTests(unittest.TestCase):
    def test_rows(self):
        self.assertEqual(sl.row_for_distance(70), 0)    # just past the dead zone
        self.assertEqual(sl.row_for_distance(130), 1)   # middle of play area
        self.assertEqual(sl.row_for_distance(190), 2)   # back of play area
        self.assertEqual(sl.row_for_distance(40), 0)    # dead zone clamps to front row
        self.assertEqual(sl.row_for_distance(260), 2)

    def test_hysteresis(self):
        boundary = sl.DEAD_ZONE_CM + (sl.PLAY_FAR_CM - sl.DEAD_ZONE_CM) / 3
        self.assertEqual(sl.row_for_distance(boundary + 2, previous_row=0), 0)
        self.assertEqual(sl.row_for_distance(boundary + 8, previous_row=0), 1)


class LinkTests(unittest.TestCase):
    def test_status_and_timeout(self):
        link, clock, _ = make_link()
        self.assertEqual(link.status(), {1: False, 2: False, 3: False})
        feed_all(link, {1: -1, 2: -1, 3: -1}, times=1)
        self.assertTrue(link.all_online())
        clock.t += sl.ONLINE_TIMEOUT_S + 0.1
        self.assertEqual(link.status(), {1: False, 2: False, 3: False})

    def test_every_hole(self):
        link, clock, _ = make_link()
        for row, distance in enumerate((83, 130, 177)):
            for sid, col in sl.COLUMN_FOR_SENSOR.items():
                readings = {s: (distance * 10 if s == sid else -1) for s in sl.SENSOR_IDS}
                feed_all(link, readings)
                self.assertEqual(link.player_zone(), (col, row))
                self.assertEqual(link.hole_index(), row * 3 + col)

    def test_nobody_there(self):
        link, _, _ = make_link()
        feed_all(link, {1: -1, 2: -1, 3: -1})
        self.assertIsNone(link.player_zone())
        self.assertIsNone(link.hole_index())

    def test_median_rejects_spike(self):
        link, _, _ = make_link()
        for mm in (1300, 1300, 600, 1300, 1300):   # one bad 60 cm reading
            link.feed(f"2,{mm}".encode())
        self.assertAlmostEqual(link.distance_cm(2), 130.0)
        self.assertFalse(link.too_close())

    def test_closest_sensor_wins_and_column_hysteresis(self):
        link, _, _ = make_link()
        feed_all(link, {1: 1300, 2: -1, 3: -1})
        self.assertEqual(link.player_zone()[0], 0)
        # Player on the line: middle sensor also sees them, only 5 cm closer -> stay left.
        feed_all(link, {1: 1300, 2: 1250, 3: -1})
        self.assertEqual(link.player_zone()[0], 0)
        # Clearly in the middle now.
        feed_all(link, {1: -1, 2: 1250, 3: -1})
        self.assertEqual(link.player_zone()[0], 1)

    def test_too_close(self):
        link, _, _ = make_link()
        feed_all(link, {1: -1, 2: 450, 3: -1})
        self.assertTrue(link.too_close())
        feed_all(link, {1: -1, 2: 650, 3: -1})
        self.assertFalse(link.too_close())

    def test_whack_needs_dwell_and_fires_once(self):
        link, clock, _ = make_link()
        feed_all(link, {1: -1, 2: 1300, 3: -1})
        self.assertFalse(link.take_whack())             # just arrived
        clock.t += sl.WHACK_DWELL_S + 0.01
        link.poll()
        self.assertTrue(link.take_whack())              # held still -> whack
        clock.t += 2.0
        link.feed(b"2,1300")
        link.poll()
        self.assertFalse(link.take_whack())             # standing still doesn't repeat
        feed_all(link, {1: 1300, 2: -1, 3: -1})          # step to another hole
        clock.t += sl.WHACK_DWELL_S + 0.01
        link.poll()
        self.assertTrue(link.take_whack())

    def test_no_whack_in_dead_zone(self):
        link, clock, _ = make_link()
        feed_all(link, {1: -1, 2: 400, 3: -1})
        clock.t += 1.0
        link.poll()
        self.assertFalse(link.take_whack())

    def test_buzzer_commands(self):
        link, clock, sock = make_link()
        link.set_buzzer(True)
        link.poll()
        self.assertEqual(sock.sent, [])                 # buzzer box IP not known yet
        feed_all(link, {1: -1, 2: 400, 3: -1})
        bid = sl.BUZZER_SENSOR_ID
        self.assertEqual(sock.sent[-1], (b"BUZZ 1", (f"10.0.0.{bid}", sl.BUZZER_PORT)))
        count = len(sock.sent)
        link.poll()
        self.assertEqual(len(sock.sent), count)          # no spam within resend window
        clock.t += sl.BUZZER_RESEND_S + 0.01
        link.poll()
        self.assertEqual(len(sock.sent), count + 1)      # keep-alive
        link.set_buzzer(False)
        link.poll()
        self.assertEqual(sock.sent[-1][0], b"BUZZ 0")


class RealSocketTest(unittest.TestCase):
    def test_udp_round_trip(self):
        try:
            link = sl.SensorLink(port=0)
        except OSError as exc:
            self.skipTest(str(exc))
        port = link._sock.getsockname()[1]
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for _ in range(sl.MEDIAN_WINDOW):
            sender.sendto(b"3,1800", ("127.0.0.1", port))
        import time
        deadline = time.monotonic() + 1.0
        while link.packets_received < sl.MEDIAN_WINDOW and time.monotonic() < deadline:
            link.poll()
        self.assertEqual(link.player_zone(), (2, 2))
        sender.close()
        link.close()


if __name__ == "__main__":
    unittest.main()
