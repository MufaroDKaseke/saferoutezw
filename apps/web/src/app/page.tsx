import { redirect } from "next/navigation";

export default function Home() {
  redirect("/dashboard"); // in newsroom mode /dashboard is the News Monitor overview
}
