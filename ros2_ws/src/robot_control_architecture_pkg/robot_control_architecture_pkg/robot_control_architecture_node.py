import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from vision_msgs.msg import Detection2DArray
from std_msgs.msg import String
from rclpy.duration import Duration
import random
import os
import time
from geometry_msgs.msg import Twist
import math
import subprocess


class SquidGameNode(Node):
    def __init__(self):
        super().__init__("squid_game")
        self.vel_pub = self.create_publisher(Twist, "cmd_vel", 10)
        self.state = "INSTRUCTIONS"  # Changed initial state
        self.time_limit = 120.0
        self.elapsed_time = 0.0
        self.game_start_time = None

        self.current_light_duration = 0.0
        self.light_end_time = None

        self.movement_threshold = 10.0
        self.size_y_finish_line = 400.0
        self.player_reached_finish_line = False
        self.player_moved = False
        self.rotation_speed = 1.0

        self.previous_detection = None
        self.current_detection = None

        self.random_interval_min = 0.8
        self.random_interval_max = 1.2

        self.detection_sub = self.create_subscription(
            Detection2DArray,
            "/color/mobilenet_detections",
            self.detection_callback,
            qos_profile_sensor_data,
        )

        self.state_pub = self.create_publisher(String, "game_state", 10)
        self.timer = self.create_timer(0.1, self.main_loop)
        self.get_logger().info("Squid Game Node Initialized.")

    def speak_text(self, text):
        """Use espeak for text-to-speech"""
        try:
            subprocess.run(["espeak", "-v", "en-us", "-s", "150", text])
        except Exception as e:
            self.get_logger().error(f"TTS error: {str(e)}")

    def main_loop(self):
        if self.state == "INSTRUCTIONS":
            self.instructions_state()
        elif self.state == "COUNTDOWN":
            self.countdown_state()
        elif self.state == "INIT":
            self.init_state()
        elif self.state == "GREEN_LIGHT":
            self.green_light_state()
        elif self.state == "RED_LIGHT":
            self.red_light_state()
        elif self.state == "GAME_OVER":
            self.game_over_state()
        else:
            self.get_logger().error(f"Unknown state: {self.state}")

    def instructions_state(self):
        """Play game instructions using TTS"""
        instructions = [
            "Welcome to Red Light Green Light.",
            "The rules are simple.",
            "When you hear Green Light, you can move forward.",
            "When you hear Red Light, you must freeze.",
            "If you move during Red Light, you will be eliminated.",
            "Reach the finish line to win.",
            "You have 2 minutes to complete the game.",
            "Get ready!",
        ]

        for instruction in instructions:
            self.speak_text(instruction)
            time.sleep(0.5)  # Pause between sentences

        self.perform_180_rotation()

        self.state = "COUNTDOWN"
        self.get_logger().info("Instructions completed, starting countdown.")

    def countdown_state(self):
        """Countdown from 3 before starting the game"""
        for count in range(3, 0, -1):
            self.speak_text(str(count))
            time.sleep(1)

        self.speak_text("Begin!")
        self.state = "INIT"
        self.get_logger().info("Countdown completed, starting game.")

    def init_state(self):
        self.get_logger().info("Game Starting.")
        self.game_start_time = self.get_clock().now()
        self.elapsed_time = 0.0
        self.start_random_light()

    def start_random_light(self):
        """
        Choose next light based on current state:
        - After GREEN_LIGHT: must be RED_LIGHT
        - After RED_LIGHT: can be either GREEN_LIGHT or RED_LIGHT
        """
        if self.state == "GREEN_LIGHT":
            # Must switch to red light after green
            self.start_red_light()
        elif self.state == "RED_LIGHT":
            # Randomly choose next light after red
            if random.choice([True, False]):
                self.start_green_light()
            else:
                self.start_red_light()
        else:
            # Initial state - randomly choose first light
            if random.choice([True, False]):
                self.start_green_light()
            else:
                self.start_red_light()

    def start_green_light(self):
        self.state = "GREEN_LIGHT"
        self.current_light_duration = random.uniform(
            self.random_interval_min, self.random_interval_max
        )
        duration = Duration(seconds=self.current_light_duration)
        self.light_end_time = self.get_clock().now() + duration
        os.system("mpg123 green_light.mp3")
        self.get_logger().info(
            f"GREEN_LIGHT state for {self.current_light_duration:.2f} seconds."
        )
        self.publish_state("GREEN_LIGHT")

    def green_light_state(self):
        now = self.get_clock().now()
        self.elapsed_time = (now - self.game_start_time).nanoseconds / 1e9

        if self.elapsed_time >= self.time_limit:
            self.speak_text("Time's up! Game Over!")
            self.get_logger().info("Time limit reached. Player loses.")
            self.state = "GAME_OVER"
            self.game_result = "LOSE"
            return

        if self.player_reached_finish_line:
            self.speak_text("Congratulations! You've won!")
            self.get_logger().info("Player reached finish line. Player wins!")
            self.state = "GAME_OVER"
            self.game_result = "WIN"
            return

        if now >= self.light_end_time:
            self.start_random_light()

    def start_red_light(self):
        self.state = "RED_LIGHT"
        self.current_light_duration = random.uniform(
            self.random_interval_min, self.random_interval_max
        )
        duration = Duration(seconds=self.current_light_duration)
        self.light_end_time = self.get_clock().now() + duration
        os.system("mpg123 red_light.mp3")
        self.get_logger().info(
            f"RED_LIGHT state for {self.current_light_duration:.2f} seconds."
        )
        self.previous_detection = None
        self.player_moved = False
        self.publish_state("RED_LIGHT")

    def red_light_state(self):
        now = self.get_clock().now()
        self.elapsed_time = (now - self.game_start_time).nanoseconds / 1e9

        if self.elapsed_time >= self.time_limit:
            self.speak_text("Time's up! Game Over!")
            self.get_logger().info("Time limit reached. Player loses.")
            self.state = "GAME_OVER"
            self.game_result = "LOSE"
            return

        if self.player_moved:
            self.perform_180_rotation()
            os.system("mpg123 lose.mp3")
            self.speak_text("Movement detected! You're eliminated!")
            self.get_logger().info("Player moved during RED_LIGHT. Player loses.")
            self.state = "GAME_OVER"
            self.game_result = "LOSE"
            return

        if now >= self.light_end_time:
            self.start_random_light()

    def perform_180_rotation(self):
        rotation_duration = math.pi / self.rotation_speed
        start_time = time.time()

        while time.time() < start_time + rotation_duration:
            vel_msg = Twist()
            vel_msg.angular.z = self.rotation_speed
            self.vel_pub.publish(vel_msg)
            time.sleep(0.1)

        vel_msg = Twist()
        vel_msg.angular.z = 0.0
        self.vel_pub.publish(vel_msg)
        self.get_logger().info("180-degree rotation completed.")

    def game_over_state(self):
        if self.game_result == "WIN":
            self.get_logger().info("Game Over: Player Wins!")
        else:
            self.get_logger().info("Game Over: Player Loses.")
        self.publish_state("GAME_OVER")
        self.timer.cancel()

    def detection_callback(self, msg):
        person_detected = False
        max_size_y = 0.0
        detection = None

        for det in msg.detections:
            for result in det.results:
                if result.hypothesis.class_id == "15":
                    bbox = det.bbox
                    size_y = bbox.size_y
                    if size_y > max_size_y:
                        person_detected = True
                        detection = det
                        max_size_y = size_y

        if person_detected:
            self.current_detection = detection
            if self.current_detection.bbox.size_y >= self.size_y_finish_line:
                self.player_reached_finish_line = True

            if self.state == "RED_LIGHT":
                if self.previous_detection is not None:
                    moved = self.detect_movement(
                        self.previous_detection, self.current_detection
                    )
                    if moved:
                        self.player_moved = True

            self.previous_detection = self.current_detection

    def detect_movement(self, prev_det, curr_det):
        prev_bbox = prev_det.bbox
        curr_bbox = curr_det.bbox

        delta_x = abs(curr_bbox.center.position.x - prev_bbox.center.position.x)
        delta_y = abs(curr_bbox.center.position.y - prev_bbox.center.position.y)
        delta_size_x = abs(curr_bbox.size_x - prev_bbox.size_x)
        delta_size_y = abs(curr_bbox.size_y - prev_bbox.size_y)

        if (
            delta_x > self.movement_threshold
            or delta_y > self.movement_threshold
            or delta_size_x > self.movement_threshold
            or delta_size_y > self.movement_threshold
        ):
            self.get_logger().info(
                f"Movement detected: delta_x={delta_x}, delta_y={delta_y}, delta_size_x={delta_size_x}, delta_size_y={delta_size_y}"
            )
            return True
        return False

    def publish_state(self, state):
        msg = String()
        msg.data = state
        self.state_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    squid_game_node = SquidGameNode()
    rclpy.spin(squid_game_node)
    squid_game_node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
