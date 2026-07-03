use std::time::{Duration, Instant};

use winit::application::ApplicationHandler;
use winit::event::WindowEvent;
use winit::event_loop::{ActiveEventLoop, ControlFlow, EventLoop};
use winit::window::{Window, WindowAttributes, WindowId};

struct App {
    window: Option<Window>,
    started: Instant,
    deadline: Instant,
}

impl ApplicationHandler for App {
    fn resumed(&mut self, event_loop: &ActiveEventLoop) {
        eprintln!("[winit-smoke] resumed at {:?}", self.started.elapsed());
        let w = event_loop
            .create_window(
                WindowAttributes::default()
                    .with_title("winit smoke")
                    .with_inner_size(winit::dpi::LogicalSize::new(400.0, 300.0)),
            )
            .expect("create_window");
        self.window = Some(w);
    }

    fn window_event(&mut self, el: &ActiveEventLoop, _id: WindowId, event: WindowEvent) {
        if matches!(event, WindowEvent::CloseRequested) {
            el.exit();
        }
    }

    fn about_to_wait(&mut self, el: &ActiveEventLoop) {
        if Instant::now() >= self.deadline {
            eprintln!(
                "[winit-smoke] deadline reached at {:?}",
                self.started.elapsed()
            );
            el.exit();
        }
    }

    fn new_events(&mut self, el: &ActiveEventLoop, _: winit::event::StartCause) {
        el.set_control_flow(ControlFlow::Poll);
    }
}

fn main() {
    eprintln!("[winit-smoke] building EventLoop");
    let el = EventLoop::new().expect("event loop");
    el.set_control_flow(ControlFlow::Poll);
    eprintln!("[winit-smoke] EventLoop built; running");
    let started = Instant::now();
    let mut app = App {
        window: None,
        started,
        deadline: started + Duration::from_millis(1500),
    };
    el.run_app(&mut app).expect("run_app");
    eprintln!("[winit-smoke] exited after {:?}", started.elapsed());
}
