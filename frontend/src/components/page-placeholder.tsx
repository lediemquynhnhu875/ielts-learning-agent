/** Trang tạm cho các mục chưa xây dựng: chỉ có tiêu đề. */
export function PagePlaceholder({ title }: { title: string }) {
  return (
    <section className="glass rounded-[32px] px-10 py-9">
      <h1 className="text-[38px] font-extrabold tracking-tight">{title}</h1>
    </section>
  );
}
