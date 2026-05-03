async function save_parameters(event) {
	if (event) {
		event.preventDefault();
	}
	var changes = [];
	const params = document.querySelectorAll(".parameter");
	for (const param of params) {
		let td = param.querySelectorAll("td");
		const name = td[0];
		const input = param.querySelectorAll("input");
		const val = input[0];
		changes.push({ name: name.textContent, val: val.value });
	}
	if (changes.length) {
		try {
			const resp = await post_json("/api/save_parameters", changes);
			if (!resp.err) {
				await update_parameters();
			} else {
				alert("The following parameters are not valid floating point numbers:\n"
					+ resp.err.join(", "));
			}
		} catch (err) {
			console.log(err);
		}
	}
}

async function update_parameters() {
	try {
		const parameters_request = await (await fetch('/api/get_parameters')).json();
		const parameters = document.getElementById("parameters")
		parameters.textContent = "";
		if (parameters_request.err) {
			return;
		}
		for (const parameter of parameters_request) {
			format_parameter(parameter);
		}
	} catch (err) {
		console.log(err);
	}
}

function format_parameter(parameter) {
	const parameters = document.getElementById("parameters");
	const parameter_templ = document.getElementById("parameter");

	const new_row = parameter_templ.content.cloneNode(true);
	let td = new_row.querySelectorAll("td");
	td[0].textContent = parameter.name;
	let input = new_row.querySelectorAll("input");
	input[0].value = parameter.val;

	parameters.appendChild(new_row);
}

document.addEventListener('DOMContentLoaded', async function () {
	await update_parameters();
}, false);