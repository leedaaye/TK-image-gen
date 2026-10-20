# API 契约 v1

所有路径 /api，JSON snake_case。认证使用 HttpOnly session cookie。错误为 {detail: string}。列表直接返回数组。ID 为 UUID 字符串。日期 ISO8601。

## 认证
- GET /auth/status -> {authenticated:bool, setup_required:bool}
- POST /auth/setup {password} 首次设置管理员密码，登录；POST /auth/login {password}；POST /auth/logout。
- GET /health -> {status:"ok",database:"sqlite"|"postgresql",worker_alive:bool}

## 商品
- GET /products?q= -> Product[]
- POST /products {name,description,category,sku,features,constraints,price,currency} -> Product
- GET /products/{id} -> Product; PATCH 同字段；DELETE 归档
- POST /products/{id}/images multipart files 多图 -> Product
- DELETE /products/{id}/images/{image_id} -> Product
- PATCH /products/{id}/images/{image_id} {role} -> Product
Product={id,name,description,category,sku,features,constraints,price,currency,created_at,images:[{id,url,role,filename}]}，文本字段默认空字符串。

## 模型设置
- GET /settings -> {analysis: Provider,image:Provider}
- PUT /settings {analysis: Provider,image:Provider} -> 同 GET
Provider={base_url,model,api_key:string(读取为空),has_key:bool,timeout:180,concurrency:2,mode:"reference"|"background",extra:object}；analysis.mode 无意义。更新 api_key 空字符串保持旧值，clear_key:true 清除。
- POST /settings/test/{analysis|image} -> {ok:bool,message:string}；image 实际生图一次产生费用，前端需明确标记。
分析使用 chat/completions（支持视觉）；生图 reference 使用 images/edits multipart 附 image[]；background 使用 images/generations。extra 作为额外请求参数。

## 项目与任务
- GET /projects -> Project[]
- POST /projects {product_id,market,language,image_count:4..10,style,brief,auto_generate:bool} -> Project（创建 planning 任务）
- GET /projects/{id} -> Project
- PATCH /projects/{id} {title?,caption?,tags?,style?,slides?:[{id,title,body,prompt}]} -> Project
- POST /projects/{id}/generate {slide_ids?:string[]} -> Project（省略表示所有未完成图片；需已有策划）
- POST /projects/{id}/replan -> Project
- POST /projects/{id}/slides/{slide_id}/regenerate {instruction:string} -> Project
- PATCH /projects/{id}/slides/{slide_id} {title?,body?,selected_version_id?} -> Project（文案变更重排当前版本，不调用模型）
- DELETE /projects/{id} 删除作品，忙碌状态拒绝
- GET /projects/{id}/export?slide_ids=id,id&include_bases=true -> ZIP
Project={id,title,product_id,product_name,market,language,image_count,style,brief,auto_generate,status:"planning"|"draft"|"generating"|"ready"|"failed",caption,tags:string[],analysis:object,error,created_at,slides:Slide[]}
Slide={id,position,title,body,prompt,status:"pending"|"queued"|"generating"|"ready"|"failed",error,selected_version_id,url:string|null,versions:[{id,url,base_url,created_at,instruction}]}
- GET /tasks -> Task[] 最近100条
Task={id,project_id,slide_id,type:"plan"|"image",status:"queued"|"running"|"completed"|"failed",error,created_at,updated_at}
- POST /tasks/{id}/retry -> Task（重新排队，防重复）
- GET /files/{path} 认证后文件读取，限制根目录，不允许路径穿越。

前端每3秒轮询活动项目和任务；所有图片 URL 是受认证的 /api/files/ 相对路径。API 不含 /api 前缀的另一种实现不接受。
